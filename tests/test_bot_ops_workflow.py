"""Tests for admin ops channel Permit/Deny workflow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import User

from singulr.bot.handlers import apply_verification_decision, on_callback
from singulr.config import get_settings
from singulr.models import Profile
from singulr.services.social_profile import SocialProfileResult
from singulr.services.telegram_actions import log_to_ops_channel


def _mock_app() -> MagicMock:
    """Build a mocked Telegram Application with async bot methods."""
    app = MagicMock()
    app.bot.send_message = AsyncMock()
    return app


def _mock_ops_admin_query(data: str) -> MagicMock:
    """Build callback query mock where sender is channel administrator."""
    query = MagicMock()
    query.data = data
    query.answer = AsyncMock()
    query.from_user = MagicMock()
    query.from_user.id = 1
    query.get_bot = MagicMock()
    query.get_bot.return_value.get_chat_member = AsyncMock(
        return_value=MagicMock(status="administrator")
    )
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
    return query


@pytest.mark.asyncio
async def test_log_to_ops_channel_uses_env_admin_ops_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """log_to_ops_channel posts to ADMIN_OPS_CHAT_ID when configured."""
    monkeypatch.setenv("ADMIN_OPS_CHAT_ID", "-100888777")
    get_settings.cache_clear()
    app = _mock_app()

    await log_to_ops_channel(
        app,
        "PENDING_REVIEW",
        channel_id=42,
        user_id=501,
        reason="Possible ban evasion",
        risk_factors=["keystroke_similarity:0.87"],
    )

    app.bot.send_message.assert_awaited_once()
    call = app.bot.send_message.await_args
    assert call.kwargs["chat_id"] == -100888777
    markup = call.kwargs.get("reply_markup")
    assert markup is not None
    row = markup.inline_keyboard[0]
    assert row[0].callback_data == "permit_42_501"
    assert row[1].callback_data == "deny_42_501"


@pytest.mark.asyncio
async def test_log_to_ops_channel_includes_join_burst_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ops alerts include join burst context when burst risk factor is present."""
    monkeypatch.setenv("ADMIN_OPS_CHAT_ID", "-100888777")
    monkeypatch.setenv("JOIN_BURST_THRESHOLD", "10")
    monkeypatch.setenv("JOIN_BURST_WINDOW_SECONDS", "300")
    get_settings.cache_clear()
    app = _mock_app()

    await log_to_ops_channel(
        app,
        "PENDING_REVIEW",
        channel_id=42,
        user_id=501,
        reason="Elevated risk — review recommended",
        risk_factors=["join_burst:12"],
    )

    message = app.bot.send_message.await_args.kwargs["text"]
    assert "Join burst: 12 joins in 300s window (threshold 10)" in message


@pytest.mark.asyncio
async def test_pending_verification_does_not_ban_until_deny(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pending path holds user and posts Permit/Deny without banning."""
    monkeypatch.setenv("ADMIN_OPS_CHAT_ID", "-100888777")
    get_settings.cache_clear()
    app = _mock_app()
    ban_member = AsyncMock()
    grant_access = AsyncMock()
    notify = AsyncMock()

    monkeypatch.setattr("singulr.bot.handlers.ban_member", ban_member)
    monkeypatch.setattr("singulr.bot.handlers.grant_access", grant_access)
    monkeypatch.setattr("singulr.bot.handlers.notify_user_result", notify)

    await apply_verification_decision(
        app,
        decision="pending",
        telegram_user_id=601,
        channel_id=42,
        reason="Possible ban evasion — keystroke_similarity",
        risk_factors=["keystroke_similarity:0.87"],
    )

    ban_member.assert_not_awaited()
    grant_access.assert_not_awaited()
    notify.assert_awaited_once()
    assert notify.await_args.kwargs.get("held") is True
    app.bot.send_message.assert_awaited_once()
    markup = app.bot.send_message.await_args.kwargs.get("reply_markup")
    assert markup is not None


@pytest.mark.asyncio
async def test_auto_deny_block_posts_audit_without_permit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto-deny block bans user and posts audit-only ops message."""
    monkeypatch.setenv("ADMIN_OPS_CHAT_ID", "-100888777")
    get_settings.cache_clear()
    app = _mock_app()
    ban_member = AsyncMock()
    notify = AsyncMock()
    notify_denied = AsyncMock()

    monkeypatch.setattr("singulr.bot.handlers.ban_member", ban_member)
    monkeypatch.setattr("singulr.bot.handlers.notify_user_result", notify)
    monkeypatch.setattr("singulr.bot.handlers.notify_user_denied", notify_denied)
    monkeypatch.setattr(
        "singulr.bot.handlers._ban_history_for_fingerprint",
        AsyncMock(return_value=None),
    )

    await apply_verification_decision(
        app,
        decision="block",
        telegram_user_id=602,
        channel_id=42,
        reason="Ban evasion — high keystroke similarity",
        fingerprint_hash="0x" + "aa" * 32,
    )

    ban_member.assert_awaited_once_with(app, 42, 602)
    notify.assert_awaited_once()
    assert notify.await_args.kwargs.get("approved") is False
    app.bot.send_message.assert_awaited_once()
    markup = app.bot.send_message.await_args.kwargs.get("reply_markup")
    assert markup is not None
    assert "More details" in str(markup)
    assert "BAN EVASION" in app.bot.send_message.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_permit_callback_grants_access_and_dms_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """Permit callback grants channel access and notifies the user."""
    grant_access = AsyncMock()
    notify = AsyncMock()
    monkeypatch.setattr("singulr.bot.handlers.grant_access", grant_access)
    monkeypatch.setattr("singulr.bot.handlers.notify_user_result", notify)

    query = _mock_ops_admin_query("permit_42_701")
    update = MagicMock()
    update.callback_query = query
    context = MagicMock()
    context.application = _mock_app()

    await on_callback(update, context)

    grant_access.assert_awaited_once_with(context.application, 42, 701)
    notify.assert_awaited_once_with(context.application, 701, approved=True)


@pytest.mark.asyncio
async def test_deny_callback_dms_denial_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deny callback bans user and sends a denial reason DM."""
    ban_member = AsyncMock()
    notify_denied = AsyncMock()
    monkeypatch.setattr("singulr.bot.handlers.ban_member", ban_member)
    monkeypatch.setattr("singulr.bot.handlers.notify_user_denied", notify_denied)

    query = _mock_ops_admin_query("deny_42_702")
    update = MagicMock()
    update.callback_query = query
    context = MagicMock()
    context.application = _mock_app()

    await on_callback(update, context)

    ban_member.assert_awaited_once_with(context.application, 42, 702)
    notify_denied.assert_awaited_once()
    assert notify_denied.await_args.args[1] == 702
    assert "denied" in notify_denied.await_args.args[2].lower()


@pytest.mark.asyncio
async def test_details_callback_replies_with_profile_for_admin(
    db_session: AsyncSession,
) -> None:
    """More details callback posts expanded admin profile card."""
    db_session.add(
        Profile(
            telegram_user_id=701,
            fingerprint_hash="0x" + "a" * 64,
            keystroke_profile={"rhythm": [1.0]},
            device_type="mobile",
        )
    )
    await db_session.commit()

    target_user = User(id=701, is_bot=False, first_name="Target", username="targetuser")
    query = _mock_ops_admin_query("details_42_701")
    update = MagicMock()
    update.callback_query = query
    context = MagicMock()
    context.application = _mock_app()
    context.application.bot.get_chat_member = AsyncMock(
        return_value=MagicMock(user=target_user)
    )
    context.application.bot.get_chat = AsyncMock(return_value=MagicMock(title="Test Channel"))
    social = SocialProfileResult(
        risk_score=10,
        soft_signals=["new_account"],
        summary="Telegram account looks new",
        sources=["telegram"],
    )

    with patch("singulr.bot.handlers.SessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "singulr.bot.handlers.analyze_social_profile",
            new_callable=AsyncMock,
            return_value=social,
        ):
            with patch(
                "singulr.bot.handlers.get_channel_title",
                new_callable=AsyncMock,
                return_value="Test Channel",
            ):
                with patch(
                    "singulr.bot.handlers._ban_history_for_fingerprint",
                    AsyncMock(return_value=None),
                ):
                    await on_callback(update, context)

    query.message.reply_text.assert_awaited_once()
    body = query.message.reply_text.await_args.args[0]
    assert "701" in body
    assert "@targetuser" in body
    assert "Social profile: Telegram account looks new" in body


@pytest.mark.asyncio
async def test_details_callback_rejects_non_admin() -> None:
    """Non-admins cannot fetch the expanded profile card."""
    query = MagicMock()
    query.data = "details_42_703"
    query.answer = AsyncMock()
    query.from_user = MagicMock()
    query.from_user.id = 99
    query.get_bot = MagicMock()
    query.get_bot.return_value.get_chat_member = AsyncMock(
        return_value=MagicMock(status="member")
    )
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
    update = MagicMock()
    update.callback_query = query
    context = MagicMock()
    context.application = _mock_app()

    await on_callback(update, context)

    query.message.reply_text.assert_awaited_once()
    assert "administrators" in query.message.reply_text.await_args.args[0].lower()
