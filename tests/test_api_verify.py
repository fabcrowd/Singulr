"""API tests for /api/verify precheck and submit."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.config import VERIFICATION_SENTENCE
from singulr.models import Ban
from singulr.services.hashing import hash_fingerprint
from singulr.services.matching import Decision, MatchResult
from singulr.services.tokens import create_token

_SAMPLE_KEYSTROKES = [
    {"key": "W", "down": 0, "up": 80, "flight": 0},
    {"key": "e", "down": 120, "up": 190, "flight": 40},
    {"key": "l", "down": 250, "up": 310, "flight": 60},
]


def _submit_body(
    token: str,
    *,
    typed_text: str | None = None,
    privacy_accepted: bool = True,
    env_flags: dict | None = None,
) -> dict:
    """Build a valid submit payload with optional overrides."""
    body = {
        "token": token,
        "visitor_id": "visitor-api-test",
        "device_type": "desktop",
        "typed_text": typed_text if typed_text is not None else VERIFICATION_SENTENCE,
        "keystrokes": _SAMPLE_KEYSTROKES,
        "privacy_accepted": privacy_accepted,
    }
    if env_flags is not None:
        body["env_flags"] = env_flags
    return body


@pytest.mark.asyncio
async def test_precheck_blocks_when_ban_exists(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Precheck returns allowed=false when the telegram user id is banned."""
    token = await create_token(db_session, telegram_user_id=111, channel_id=42)
    db_session.add(
        Ban(
            telegram_user_id=111,
            fingerprint_hash="0x" + "a" * 64,
            reason="spam",
        )
    )
    await db_session.commit()

    response = await api_client.post(
        "/api/verify/precheck",
        json={"token": token, "visitor_id": "visitor-precheck-block"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["reason"] == "unavailable"


@pytest.mark.asyncio
async def test_precheck_blocks_banned_fingerprint_new_account(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Precheck blocks evasion: new user id but known banned device fingerprint."""
    visitor_id = "evasion-device-fingerprint"
    banned_fp = hash_fingerprint(visitor_id)
    db_session.add(
        Ban(
            telegram_user_id=9001,
            fingerprint_hash=banned_fp,
            reason="prior_ban",
        )
    )
    await db_session.commit()

    token = await create_token(db_session, telegram_user_id=9002, channel_id=42)

    response = await api_client.post(
        "/api/verify/precheck",
        json={"token": token, "visitor_id": visitor_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["reason"] == "unavailable"


@pytest.mark.asyncio
@patch("singulr.api.verify._notify_bot", new_callable=AsyncMock)
async def test_submit_rejects_reused_token(
    _mock_notify: AsyncMock,
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Second submit with the same token returns link_expired (410)."""
    token = await create_token(db_session, telegram_user_id=223, channel_id=42)

    first = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(token),
    )
    assert first.status_code == 200

    second = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(token),
    )
    assert second.status_code == 410
    assert second.json()["detail"] == "link_expired"


@pytest.mark.asyncio
async def test_submit_rejects_wrong_sentence(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Submit rejects when typed text does not match the verification sentence."""
    token = await create_token(db_session, telegram_user_id=222, channel_id=42)

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(token, typed_text="I am definitely not reading the rules."),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "sentence_mismatch"


@pytest.mark.asyncio
@patch("singulr.api.verify._notify_bot", new_callable=AsyncMock)
async def test_submit_approves_clean_user(
    mock_notify: AsyncMock,
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Submit approves a user with no ban signals."""
    token = await create_token(db_session, telegram_user_id=333, channel_id=99)

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "approve"
    assert body["telegram_user_id"] == 333
    assert body["channel_id"] == 99
    mock_notify.assert_awaited_once()


@pytest.mark.asyncio
@patch("singulr.api.verify._notify_bot", new_callable=AsyncMock)
async def test_submit_accepts_env_flags(
    mock_notify: AsyncMock,
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Submit accepts env_flags and approves when signals are clean."""
    token = await create_token(db_session, telegram_user_id=444, channel_id=99)

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(
            token,
            env_flags={"webdriver": False, "headless_ua": False},
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "approve"
    mock_notify.assert_awaited_once()


@pytest.mark.asyncio
@patch("singulr.api.verify._notify_bot", new_callable=AsyncMock)
async def test_submit_flags_env_anomaly_when_webdriver(
    mock_notify: AsyncMock,
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Submit flags env_anomaly when navigator.webdriver is reported."""
    token = await create_token(db_session, telegram_user_id=555, channel_id=99)

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(
            token,
            env_flags={"webdriver": True, "headless_ua": False},
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "flag"
    assert any("env_anomaly" in factor for factor in body["risk_factors"])
    mock_notify.assert_awaited_once()


@pytest.mark.asyncio
@patch("singulr.api.verify.check_known_bad", new_callable=AsyncMock)
@patch("singulr.api.verify._notify_bot", new_callable=AsyncMock)
async def test_submit_returns_pending_with_channel_policy(
    mock_notify: AsyncMock,
    mock_check: AsyncMock,
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Submit maps PENDING matching result to pending bot payload with security_preset."""
    mock_check.return_value = MatchResult(
        Decision.PENDING,
        "Possible ban evasion — keystroke_similarity",
        ["keystroke_similarity:0.87"],
        matched_ban_id=5,
    )
    token = await create_token(db_session, telegram_user_id=900, channel_id=42)

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "pending"
    assert body["security_preset"] == "balanced"
    mock_check.assert_awaited_once()
    assert mock_check.await_args.kwargs["channel_id"] == 42
    assert mock_check.await_args.kwargs["policy"].security_preset == "balanced"
    mock_notify.assert_awaited_once()
    notify_payload = mock_notify.await_args.args[0]
    assert notify_payload["decision"] == "pending"
    assert notify_payload["security_preset"] == "balanced"
    assert notify_payload["matched_ban_id"] == 5


@pytest.mark.asyncio
@patch("singulr.api.verify.check_known_bad", new_callable=AsyncMock)
@patch("singulr.api.verify._notify_bot", new_callable=AsyncMock)
async def test_submit_block_ban_evasion_auto_deny_not_pending(
    mock_notify: AsyncMock,
    mock_check: AsyncMock,
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Submit maps BLOCK ban-evasion to block bot payload, not pending."""
    mock_check.return_value = MatchResult(
        Decision.BLOCK,
        "Ban evasion — high keystroke similarity",
        ["keystroke_similarity:0.95"],
        matched_ban_id=3,
    )
    token = await create_token(db_session, telegram_user_id=901, channel_id=42)

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "block"
    assert body["decision"] != "pending"
    mock_notify.assert_awaited_once()
    notify_payload = mock_notify.await_args.args[0]
    assert notify_payload["decision"] == "block"
    assert notify_payload["security_preset"] == "balanced"


@pytest.mark.asyncio
@patch("singulr.api.verify._chain.register_fingerprint", new_callable=AsyncMock)
@patch("singulr.api.verify._notify_bot", new_callable=AsyncMock)
async def test_submit_approve_registers_fingerprint_on_chain(
    mock_notify: AsyncMock,
    mock_register: AsyncMock,
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Approve path registers fingerprint when network registry is enabled."""
    token = await create_token(db_session, telegram_user_id=1001, channel_id=42)

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(token),
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "approve"
    mock_register.assert_awaited_once()
    fingerprint_arg = mock_register.await_args.args[0]
    assert fingerprint_arg.startswith("0x")
    mock_notify.assert_awaited_once()
