"""Tests for admin-triggered reverification."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Chat, ChatJoinRequest, User

from singulr.bot.handlers import on_join_request, reverify_command
from singulr.config import VERIFICATION_SENTENCE, get_settings
from singulr.models import Profile
from singulr.services.reverification import STATUS_APPROVED, STATUS_REVERIFICATION_REQUIRED
from singulr.services.reverification import require_reverification
from singulr.services.tokens import TokenRateLimitError, create_token


def _sample_profile(telegram_user_id: int, *, status: str = STATUS_APPROVED) -> Profile:
    """Build a minimal profile row for tests."""
    return Profile(
        telegram_user_id=telegram_user_id,
        fingerprint_hash="0x" + "a" * 64,
        keystroke_profile={"dwell_mean": 100.0},
        device_type="desktop",
        status=status,
    )


@pytest.mark.asyncio
async def test_require_reverification_sets_profile_status(db_session: AsyncSession) -> None:
    """require_reverification flags an existing profile."""
    db_session.add(_sample_profile(7001))
    await db_session.commit()

    profile = await require_reverification(db_session, 7001)

    assert profile is not None
    assert profile.status == STATUS_REVERIFICATION_REQUIRED


@pytest.mark.asyncio
async def test_require_reverification_returns_none_without_profile(db_session: AsyncSession) -> None:
    """require_reverification is a no-op when the user has no profile."""
    profile = await require_reverification(db_session, 7999)
    assert profile is None


@pytest.mark.asyncio
async def test_reverify_command_rejects_non_admin(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the configured admin may run /reverify."""
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "424242")
    get_settings.cache_clear()

    update = MagicMock()
    update.effective_user = User(id=111, is_bot=False, first_name="User")
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["7001"]

    await reverify_command(update, context)

    update.message.reply_text.assert_awaited_once()
    assert "admin" in update.message.reply_text.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_reverify_command_sets_status_for_admin(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admin /reverify flags the target profile."""
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "424242")
    get_settings.cache_clear()
    db_session.add(_sample_profile(7002))
    await db_session.commit()

    update = MagicMock()
    update.effective_user = User(id=424242, is_bot=False, first_name="Admin")
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["7002"]

    with patch("singulr.bot.handlers.SessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        await reverify_command(update, context)

    row = await db_session.scalar(select(Profile).where(Profile.telegram_user_id == 7002))
    assert row is not None
    assert row.status == STATUS_REVERIFICATION_REQUIRED
    update.message.reply_text.assert_awaited_once()
    assert "7002" in update.message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_admin_api_reverify_sets_status(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST /api/admin/reverify flags a profile with X-Admin-Key."""
    db_session.add(_sample_profile(7100))
    await db_session.commit()

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ADMIN_API_KEY", "secret-admin-key")
        get_settings.cache_clear()
        response = await api_client.post(
            "/api/admin/reverify",
            json={"telegram_user_id": 7100},
            headers={"X-Admin-Key": "secret-admin-key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["telegram_user_id"] == 7100
    assert body["status"] == STATUS_REVERIFICATION_REQUIRED

    row = await db_session.scalar(select(Profile).where(Profile.telegram_user_id == 7100))
    assert row is not None
    assert row.status == STATUS_REVERIFICATION_REQUIRED


@pytest.mark.asyncio
@patch("singulr.bot.handlers.send_verification_dm", new_callable=AsyncMock)
@patch("singulr.bot.handlers.restrict_member", new_callable=AsyncMock)
@patch("singulr.bot.handlers.get_channel_title", new_callable=AsyncMock, return_value="Test Channel")
async def test_on_join_request_sends_verify_link_without_granting_access(
    mock_title: AsyncMock,
    mock_restrict: AsyncMock,
    mock_dm: AsyncMock,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Join handler restricts the user and DMs a verify link only."""
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8000")
    get_settings.cache_clear()
    db_session.add(_sample_profile(7200, status=STATUS_REVERIFICATION_REQUIRED))
    await db_session.commit()

    user = User(id=7200, is_bot=False, first_name="Member")
    chat = Chat(id=-100123, type=Chat.CHANNEL)
    request = ChatJoinRequest(chat=chat, from_user=user, date=MagicMock())
    update = MagicMock()
    update.chat_join_request = request
    context = MagicMock()
    context.application = MagicMock()

    with patch("singulr.bot.handlers.SessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        await on_join_request(update, context)

    mock_restrict.assert_awaited_once()
    mock_dm.assert_awaited_once()
    assert "verify?token=" in mock_dm.await_args.args[2]


@pytest.mark.asyncio
@patch("singulr.api.verify._notify_bot", new_callable=AsyncMock)
async def test_submit_clears_reverification_on_approve(
    mock_notify: AsyncMock,
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Successful submit clears reverification_required and approves the user."""
    db_session.add(_sample_profile(7300, status=STATUS_REVERIFICATION_REQUIRED))
    await db_session.commit()
    token = await create_token(db_session, telegram_user_id=7300, channel_id=42)

    response = await api_client.post(
        "/api/verify/submit",
        json={
            "token": token,
            "visitor_id": "visitor-reverify",
            "device_type": "desktop",
            "typed_text": VERIFICATION_SENTENCE,
            "keystrokes": [{"key": "a", "down": 0, "up": 80, "flight": 0}],
            "privacy_accepted": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "approve"
    row = await db_session.scalar(select(Profile).where(Profile.telegram_user_id == 7300))
    assert row is not None
    assert row.status == STATUS_APPROVED
    mock_notify.assert_awaited_once()


@pytest.mark.asyncio
@patch("singulr.api.verify._notify_bot", new_callable=AsyncMock)
async def test_submit_forces_pending_until_reverification_completes(
    mock_notify: AsyncMock,
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Reverification users with elevated risk stay pending instead of auto-approve."""
    db_session.add(_sample_profile(7400, status=STATUS_REVERIFICATION_REQUIRED))
    await db_session.commit()
    token = await create_token(db_session, telegram_user_id=7400, channel_id=42)

    response = await api_client.post(
        "/api/verify/submit",
        json={
            "token": token,
            "visitor_id": "visitor-reverify-flag",
            "device_type": "desktop",
            "typed_text": VERIFICATION_SENTENCE,
            "keystrokes": [{"key": "a", "down": 0, "up": 80, "flight": 0}],
            "privacy_accepted": True,
            "env_flags": {"webdriver": True, "headless_ua": False},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] in {"flag", "pending"}
    row = await db_session.scalar(select(Profile).where(Profile.telegram_user_id == 7400))
    assert row is not None
    assert row.status == STATUS_REVERIFICATION_REQUIRED
    mock_notify.assert_awaited_once()


@pytest.mark.asyncio
@patch("singulr.bot.handlers.send_verification_dm", new_callable=AsyncMock)
@patch("singulr.bot.handlers.restrict_member", new_callable=AsyncMock)
@patch("singulr.bot.handlers.get_channel_title", new_callable=AsyncMock, return_value="Test Channel")
async def test_on_join_request_dm_on_token_rate_limit(
    mock_title: AsyncMock,
    mock_restrict: AsyncMock,
    mock_dm: AsyncMock,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Token rate limit during join sends a user-facing DM instead of failing silently."""
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8000")
    get_settings.cache_clear()

    user = User(id=7500, is_bot=False, first_name="Member")
    chat = Chat(id=-100123, type=Chat.CHANNEL)
    request = ChatJoinRequest(chat=chat, from_user=user, date=MagicMock())
    update = MagicMock()
    update.chat_join_request = request
    update.effective_user = user
    context = MagicMock()
    context.application = MagicMock()
    context.application.bot = MagicMock()
    context.application.bot.send_message = AsyncMock()

    with patch("singulr.bot.handlers.SessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "singulr.bot.handlers.create_token",
            new_callable=AsyncMock,
            side_effect=TokenRateLimitError("rate limited"),
        ):
            await on_join_request(update, context)

    context.application.bot.send_message.assert_awaited_once()
    assert "try again" in context.application.bot.send_message.await_args.kwargs["text"].lower()
