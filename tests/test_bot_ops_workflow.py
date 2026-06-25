"""Tests for admin ops channel Permit/Deny workflow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from singulr.bot.handlers import apply_verification_decision, on_callback
from singulr.config import get_settings
from singulr.services.telegram_actions import log_to_ops_channel


def _mock_app() -> MagicMock:
    """Build a mocked Telegram Application with async bot methods."""
    app = MagicMock()
    app.bot.send_message = AsyncMock()
    return app


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
    assert app.bot.send_message.await_args.kwargs.get("reply_markup") is None
    assert "BAN EVASION" in app.bot.send_message.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_permit_callback_grants_access_and_dms_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """Permit callback grants channel access and notifies the user."""
    grant_access = AsyncMock()
    notify = AsyncMock()
    monkeypatch.setattr("singulr.bot.handlers.grant_access", grant_access)
    monkeypatch.setattr("singulr.bot.handlers.notify_user_result", notify)

    query = MagicMock()
    query.data = "permit_42_701"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
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

    query = MagicMock()
    query.data = "deny_42_702"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
    update = MagicMock()
    update.callback_query = query
    context = MagicMock()
    context.application = _mock_app()

    await on_callback(update, context)

    ban_member.assert_awaited_once_with(context.application, 42, 702)
    notify_denied.assert_awaited_once()
    assert notify_denied.await_args.args[1] == 702
    assert "denied" in notify_denied.await_args.args[2].lower()
