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
from verify_helpers import challenge_proof_for

_SAMPLE_KEYSTROKES = [
    {"key": "W", "down": 0, "up": 90, "flight": 0},
    {"key": "e", "down": 180, "up": 260, "flight": 90},
    {"key": "l", "down": 420, "up": 500, "flight": 160},
    {"key": "c", "down": 900, "up": 980, "flight": 400},
    {"key": "o", "down": 1500, "up": 1580, "flight": 520},
    {"key": "m", "down": 2400, "up": 2480, "flight": 820},
    {"key": "e", "down": 3200, "up": 3280, "flight": 720},
]


_VISITOR_ID = "visitor-api-test"


def _submit_body(
    token: str,
    *,
    challenge_proof: str,
    typed_text: str | None = None,
    privacy_accepted: bool = True,
    env_flags: dict | None = None,
    visitor_id: str = _VISITOR_ID,
    keystrokes: list[dict] | None = None,
) -> dict:
    """Build a valid submit payload with optional overrides."""
    body = {
        "token": token,
        "visitor_id": visitor_id,
        "device_type": "desktop",
        "typed_text": typed_text if typed_text is not None else VERIFICATION_SENTENCE,
        "keystrokes": keystrokes if keystrokes is not None else _SAMPLE_KEYSTROKES,
        "privacy_accepted": privacy_accepted,
        "challenge_proof": challenge_proof,
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
async def test_precheck_returns_challenge_secret(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Allowed precheck issues a challenge secret for submit binding."""
    token = await create_token(db_session, telegram_user_id=112, channel_id=42)

    response = await api_client.post(
        "/api/verify/precheck",
        json={"token": token, "visitor_id": "visitor-challenge"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is True
    assert body.get("challenge_secret")
    assert len(body["challenge_secret"]) >= 32


@pytest.mark.asyncio
@patch("singulr.api.verify.check_known_bad", new_callable=AsyncMock)
async def test_precheck_omits_ip_flagged_from_response(
    mock_check: AsyncMock,
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Precheck JSON does not leak ip_flagged oracle to the verify client."""
    mock_check.return_value = MatchResult(
        Decision.FLAG,
        "Elevated risk",
        ["ip_hash_match"],
    )
    token = await create_token(db_session, telegram_user_id=113, channel_id=42)

    response = await api_client.post(
        "/api/verify/precheck",
        json={"token": token, "visitor_id": "visitor-no-oracle"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is True
    assert "ip_flagged" not in body


@pytest.mark.asyncio
@patch("singulr.api.verify.allow_verify_request")
async def test_precheck_honors_trusted_proxy_for_client_ip(
    mock_allow: AsyncMock,
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """X-Forwarded-For is used only when the direct peer is a trusted proxy."""
    mock_allow.return_value = True
    token = await create_token(db_session, telegram_user_id=114, channel_id=42)
    body = {"token": token, "visitor_id": "visitor-proxy"}
    headers = {"X-Forwarded-For": "203.0.113.55"}

    with patch("singulr.api.verify.get_settings") as mock_settings:
        mock_settings.return_value.verify_rate_limit_per_minute = 30
        mock_settings.return_value.verify_precheck_per_token_per_minute = 100
        mock_settings.return_value.trusted_proxy_ip_list = []
        await api_client.post("/api/verify/precheck", json=body, headers=headers)

    assert mock_allow.call_args.args[0] == "127.0.0.1"

    mock_allow.reset_mock()
    with patch("singulr.api.verify.get_settings") as mock_settings:
        mock_settings.return_value.verify_rate_limit_per_minute = 30
        mock_settings.return_value.verify_precheck_per_token_per_minute = 100
        mock_settings.return_value.trusted_proxy_ip_list = ["127.0.0.1"]
        await api_client.post("/api/verify/precheck", json=body, headers=headers)

    assert mock_allow.call_args.args[0] == "203.0.113.55"


@pytest.mark.asyncio
async def test_submit_rejects_invalid_challenge(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Submit without valid challenge proof is rejected."""
    token = await create_token(db_session, telegram_user_id=224, channel_id=42)

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(token, challenge_proof="not-valid"),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "challenge_invalid"


@pytest.mark.asyncio
async def test_precheck_rejects_visitor_id_change_after_bind(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Second precheck with a different visitor_id is rejected."""
    token = await create_token(db_session, telegram_user_id=225, channel_id=42)

    first = await api_client.post(
        "/api/verify/precheck",
        json={"token": token, "visitor_id": "visitor-first"},
    )
    assert first.status_code == 200

    second = await api_client.post(
        "/api/verify/precheck",
        json={"token": token, "visitor_id": "visitor-second"},
    )

    assert second.status_code == 400
    assert second.json()["detail"] == "visitor_id_mismatch"


@pytest.mark.asyncio
async def test_precheck_allows_fallback_to_fingerprint_visitor_upgrade(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Precheck may upgrade from fallback fb_ visitor id to FingerprintJS id."""
    token = await create_token(db_session, telegram_user_id=226, channel_id=42)

    first = await api_client.post(
        "/api/verify/precheck",
        json={"token": token, "visitor_id": "fb_12345"},
    )
    assert first.status_code == 200

    second = await api_client.post(
        "/api/verify/precheck",
        json={"token": token, "visitor_id": "fingerprint-real-id"},
    )

    assert second.status_code == 200


@pytest.mark.asyncio
@patch("singulr.api.verify._notify_bot", new_callable=AsyncMock)
async def test_submit_visitor_id_mismatch_forces_pending(
    mock_notify: AsyncMock,
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Submit with visitor_id different from bound token value forces pending."""
    token = await create_token(db_session, telegram_user_id=227, channel_id=42)
    proof = await challenge_proof_for(
        api_client,
        token,
        visitor_id="visitor-submit",
        session=db_session,
        bound_visitor_id="visitor-bound",
    )

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(
            token,
            challenge_proof=proof,
            visitor_id="visitor-submit",
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "pending"
    assert "visitor_id_mismatch" in body.get("risk_factors", [])
    mock_notify.assert_awaited_once()


def _uniform_keystrokes(count: int = 20, flight: float = 50.0) -> list[dict]:
    return [
        {"key": "a", "down": i * flight, "up": i * flight + 40, "flight": flight}
        for i in range(count)
    ]


def _fast_keystrokes(count: int = 20) -> list[dict]:
    return [
        {"key": "a", "down": i * 10, "up": i * 10 + 8, "flight": 10}
        for i in range(count)
    ]


@pytest.mark.asyncio
async def test_submit_rejects_too_many_keystrokes(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Submit rejects payloads exceeding the keystroke event cap."""
    token = await create_token(db_session, telegram_user_id=228, channel_id=42)
    proof = await challenge_proof_for(api_client, token)
    oversized = [{"key": "a", "down": 0, "up": 1, "flight": 0}] * 501

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(token, challenge_proof=proof, keystrokes=oversized),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@patch("singulr.api.verify._notify_bot", new_callable=AsyncMock)
async def test_submit_flags_synthetic_keystroke_rhythm(
    mock_notify: AsyncMock,
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Uniform keystroke rhythm is flagged as synthetic."""
    token = await create_token(db_session, telegram_user_id=229, channel_id=42)
    proof = await challenge_proof_for(api_client, token)

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(
            token,
            challenge_proof=proof,
            keystrokes=_uniform_keystrokes(),
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "flag"
    assert "synthetic_keystroke" in body.get("risk_factors", [])
    mock_notify.assert_awaited_once()


@pytest.mark.asyncio
@patch("singulr.api.verify._notify_bot", new_callable=AsyncMock)
async def test_submit_flags_too_fast_typing(
    mock_notify: AsyncMock,
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Very fast typing sessions are flagged."""
    token = await create_token(db_session, telegram_user_id=230, channel_id=42)
    proof = await challenge_proof_for(api_client, token)

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(
            token,
            challenge_proof=proof,
            keystrokes=_fast_keystrokes(),
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "flag"
    assert "too_fast_verify" in body.get("risk_factors", [])
    mock_notify.assert_awaited_once()


@pytest.mark.asyncio
@patch("singulr.api.verify._notify_bot", new_callable=AsyncMock)
async def test_submit_rejects_reused_token(
    _mock_notify: AsyncMock,
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Second submit with the same token returns link_expired (410)."""
    token = await create_token(db_session, telegram_user_id=223, channel_id=42)
    proof = await challenge_proof_for(api_client, token)

    first = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(token, challenge_proof=proof),
    )
    assert first.status_code == 200

    second = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(token, challenge_proof=proof),
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
        json=_submit_body(
            token,
            challenge_proof="unused",
            typed_text="I am definitely not reading the rules.",
        ),
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
    proof = await challenge_proof_for(api_client, token)

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(token, challenge_proof=proof),
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
    proof = await challenge_proof_for(api_client, token)

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(
            token,
            challenge_proof=proof,
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
    proof = await challenge_proof_for(api_client, token)

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(
            token,
            challenge_proof=proof,
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
    proof = await challenge_proof_for(
        api_client, token, session=db_session
    )

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(token, challenge_proof=proof),
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
    proof = await challenge_proof_for(
        api_client, token, session=db_session
    )

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(token, challenge_proof=proof),
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
    proof = await challenge_proof_for(api_client, token)

    response = await api_client.post(
        "/api/verify/submit",
        json=_submit_body(token, challenge_proof=proof),
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "approve"
    mock_register.assert_awaited_once()
    fingerprint_arg = mock_register.await_args.args[0]
    assert fingerprint_arg.startswith("0x")
    mock_notify.assert_awaited_once()
