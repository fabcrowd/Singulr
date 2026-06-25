"""Unit tests for singulr.bot.handlers join and verification paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Update, User
from telegram.constants import ChatType

from singulr.bot.handlers import apply_verification_decision, on_join_request, start_command
from singulr.config import get_settings
from singulr.services.tokens import TokenRateLimitError


def _mock_app() -> MagicMock:
    app = MagicMock()
    app.bot.send_message = AsyncMock()
    return app


@pytest.mark.asyncio
async def test_start_command_sends_verify_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """/start creates a token and replies with the verify link."""
    monkeypatch.setenv("CHANNEL_ID", "100")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://singulr.example")
    get_settings.cache_clear()

    user = User(id=5001, is_bot=False, first_name="Test")
    chat = Chat(id=5001, type=ChatType.PRIVATE)
    message = MagicMock()
    message.reply_text = AsyncMock()
    update = Update(update_id=1, message=message)
    update._effective_user = user
    update._effective_chat = chat
    context = MagicMock()

    with patch("singulr.bot.handlers.SessionLocal") as session_local:
        session = AsyncMock()
        session_local.return_value.__aenter__ = AsyncMock(return_value=session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("singulr.bot.handlers.create_token", new_callable=AsyncMock, return_value="tok-abc"):
            await start_command(update, context)

    message.reply_text.assert_awaited_once()
    text = message.reply_text.await_args.args[0]
    assert "tok-abc" in text
    assert "https://singulr.example/verify" in text


@pytest.mark.asyncio
async def test_apply_verification_decision_approve_grants_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approve decision grants channel access and notifies the user."""
    grant_access = AsyncMock()
    notify = AsyncMock()
    log_channel = AsyncMock()
    monkeypatch.setattr("singulr.bot.handlers.grant_access", grant_access)
    monkeypatch.setattr("singulr.bot.handlers.notify_user_result", notify)
    monkeypatch.setattr("singulr.bot.handlers.log_to_channel", log_channel)

    app = _mock_app()
    await apply_verification_decision(
        app,
        decision="approve",
        telegram_user_id=5002,
        channel_id=100,
    )

    grant_access.assert_awaited_once_with(app, 100, 5002)
    notify.assert_awaited_once_with(app, 5002, approved=True)
    log_channel.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_verification_decision_flag_holds_without_ban(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag decision logs elevated risk and holds the user without banning."""
    ban_member = AsyncMock()
    grant_access = AsyncMock()
    notify = AsyncMock()
    log_channel = AsyncMock()
    monkeypatch.setattr("singulr.bot.handlers.ban_member", ban_member)
    monkeypatch.setattr("singulr.bot.handlers.grant_access", grant_access)
    monkeypatch.setattr("singulr.bot.handlers.notify_user_result", notify)
    monkeypatch.setattr("singulr.bot.handlers.log_to_channel", log_channel)

    app = _mock_app()
    await apply_verification_decision(
        app,
        decision="flag",
        telegram_user_id=5003,
        channel_id=100,
        reason="Elevated risk",
        risk_factors=["ip_velocity"],
    )

    ban_member.assert_not_awaited()
    grant_access.assert_not_awaited()
    notify.assert_awaited_once()
    assert notify.await_args.kwargs.get("held") is True
    log_channel.assert_awaited_once()


@pytest.mark.asyncio
@patch("singulr.bot.handlers.send_verification_dm", new_callable=AsyncMock)
@patch("singulr.bot.handlers.restrict_member", new_callable=AsyncMock)
@patch("singulr.bot.handlers.get_channel_title", new_callable=AsyncMock, return_value="Singulr")
async def test_on_join_request_restricts_and_dms_verify_link(
    mock_title: AsyncMock,
    mock_restrict: AsyncMock,
    mock_dm: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Join request restricts the member and sends a verification DM."""
    monkeypatch.setenv("CHANNEL_ID", "-100200")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://singulr.example")
    get_settings.cache_clear()

    user = User(id=5004, is_bot=False, first_name="Joiner")
    request = MagicMock()
    request.from_user = user
    request.chat = Chat(id=-100200, type=ChatType.CHANNEL)
    update = MagicMock()
    update.chat_join_request = request
    context = MagicMock()
    context.application = _mock_app()

    with patch("singulr.bot.handlers.SessionLocal") as session_local:
        session = AsyncMock()
        session_local.return_value.__aenter__ = AsyncMock(return_value=session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("singulr.bot.handlers.create_token", new_callable=AsyncMock, return_value="join-tok"):
            await on_join_request(update, context)

    mock_restrict.assert_awaited_once_with(context.application, -100200, 5004)
    mock_dm.assert_awaited_once()
    assert "join-tok" in mock_dm.await_args.args[2]


@pytest.mark.asyncio
async def test_start_command_handles_token_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """/start replies gracefully when the user exceeds the token quota."""
    monkeypatch.setenv("CHANNEL_ID", "100")
    get_settings.cache_clear()

    user = User(id=5005, is_bot=False, first_name="Test")
    chat = Chat(id=5005, type=ChatType.PRIVATE)
    message = MagicMock()
    message.reply_text = AsyncMock()
    update = Update(update_id=2, message=message)
    update._effective_user = user
    update._effective_chat = chat
    context = MagicMock()

    with patch("singulr.bot.handlers.SessionLocal") as session_local:
        session = AsyncMock()
        session_local.return_value.__aenter__ = AsyncMock(return_value=session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "singulr.bot.handlers.create_token",
            new_callable=AsyncMock,
            side_effect=TokenRateLimitError("quota"),
        ):
            await start_command(update, context)

    message.reply_text.assert_awaited_once()
    assert "too many" in message.reply_text.await_args.args[0].lower()
