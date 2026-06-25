"""Tests for multi-step admin ban inline callback flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.bot.ban_flow import PENDING_BAN_CATEGORY_KEY, PENDING_BAN_USER_KEY
from singulr.bot.handlers import on_callback
from singulr.config import get_settings
from singulr.domain.ban_taxonomy import BanCategory, BanSeverity
from singulr.models import Ban, Profile


def _callback_context() -> tuple[MagicMock, MagicMock]:
    """Build mocked update/context for callback tests."""
    query = MagicMock()
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
    query.message.edit_message_reply_markup = AsyncMock()
    update = MagicMock()
    update.callback_query = query
    context = MagicMock()
    context.application = MagicMock()
    context.application.bot = MagicMock()
    context.user_data = {}
    return update, context


@pytest.mark.asyncio
async def test_ban_start_shows_category_picker(monkeypatch: pytest.MonkeyPatch) -> None:
    """ban_<user_id> opens the category inline keyboard."""
    monkeypatch.setenv("CHANNEL_ID", "100")
    get_settings.cache_clear()
    update, context = _callback_context()
    update.callback_query.data = "ban_9001"

    await on_callback(update, context)

    assert context.user_data[PENDING_BAN_USER_KEY] == 9001
    update.callback_query.message.reply_text.assert_awaited_once()
    markup = update.callback_query.message.reply_text.await_args.kwargs.get("reply_markup")
    assert markup is not None
    labels = {btn.text for row in markup.inline_keyboard for btn in row}
    assert "Spam" in labels
    assert "Scam Fraud" in labels


@pytest.mark.asyncio
async def test_ban_cat_shows_severity_picker() -> None:
    """ban_cat_<category> stores category and shows severity keyboard."""
    update, context = _callback_context()
    context.user_data[PENDING_BAN_USER_KEY] = 9001
    update.callback_query.data = "ban_cat_harassment"

    await on_callback(update, context)

    assert context.user_data[PENDING_BAN_CATEGORY_KEY] == BanCategory.HARASSMENT.value
    update.callback_query.message.reply_text.assert_awaited_once()
    markup = update.callback_query.message.reply_text.await_args.kwargs.get("reply_markup")
    assert markup is not None
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "ban_sev_low" in callbacks
    assert "ban_sev_permanent" in callbacks


@pytest.mark.asyncio
async def test_ban_sev_records_ban_with_category_and_severity(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ban_sev_<severity> bans user and persists category/severity on the ban row."""
    monkeypatch.setenv("CHANNEL_ID", "100")
    get_settings.cache_clear()
    db_session.add(
        Profile(
            telegram_user_id=9001,
            fingerprint_hash="0x" + "9" * 64,
            keystroke_profile={"rhythm": [1.0]},
            device_type="desktop",
        )
    )
    await db_session.commit()

    update, context = _callback_context()
    context.user_data[PENDING_BAN_USER_KEY] = 9001
    context.user_data[PENDING_BAN_CATEGORY_KEY] = BanCategory.SCAM_FRAUD.value
    update.callback_query.data = "ban_sev_high"

    ban_member = AsyncMock()
    notify = AsyncMock()
    monkeypatch.setattr("singulr.bot.handlers.ban_member", ban_member)
    monkeypatch.setattr("singulr.bot.handlers.notify_user_result", notify)

    with patch("singulr.bot.handlers.SessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        await on_callback(update, context)

    ban_member.assert_awaited_once()
    notify.assert_awaited_once_with(context.application, 9001, approved=False)
    ban = await db_session.scalar(select(Ban).where(Ban.telegram_user_id == 9001))
    assert ban is not None
    assert ban.category == BanCategory.SCAM_FRAUD.value
    assert ban.severity == BanSeverity.HIGH.value
    assert PENDING_BAN_USER_KEY not in context.user_data
    assert PENDING_BAN_CATEGORY_KEY not in context.user_data
