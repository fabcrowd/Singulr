"""Tests for /security setup wizard."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Chat, Message, Update, User
from telegram.constants import ChatType

from singulr.bot.security_wizard import (
    WIZARD_CHANNEL_KEY,
    WIZARD_EVASION_KEY,
    WIZARD_OPS_KEY,
    WIZARD_PRESET_KEY,
    WizardState,
    confirm_selected,
    evasion_selected,
    ops_selected,
    preset_selected,
    security_command,
)
from singulr.config import get_settings
from singulr.models import ChannelSecuritySettings
from singulr.services.channel_policy import resolve_wizard_thresholds, upsert_channel_security_settings


def _private_update(*, user_id: int = 4242) -> MagicMock:
    """Build a private-chat update with a mock message."""
    update = MagicMock()
    update.effective_user = User(id=user_id, is_bot=False, first_name="Admin")
    update.effective_chat = Chat(id=user_id, type=ChatType.PRIVATE)
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


def _callback_update(data: str, *, user_id: int = 4242) -> Update:
    """Build an update with callback_query."""
    user = User(id=user_id, is_bot=False, first_name="Admin")
    chat = Chat(id=user_id, type=ChatType.PRIVATE)
    query = MagicMock()
    query.data = data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.from_user = user
    query.message = Message(message_id=2, date=MagicMock(), chat=chat)
    update = Update(update_id=2, callback_query=query)
    return update


@pytest.mark.asyncio
async def test_security_rejects_non_private_chat() -> None:
    """Wizard only runs in a private DM."""
    update = MagicMock()
    update.effective_chat = Chat(id=-100, type=ChatType.CHANNEL)
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    result = await security_command(update, context)

    assert result == -1
    update.message.reply_text.assert_awaited_once()
    assert "private" in update.message.reply_text.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_security_rejects_non_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-admins cannot start the wizard."""
    monkeypatch.setenv("CHANNEL_ID", "100")
    get_settings.cache_clear()
    update = _private_update()
    context = MagicMock()
    context.user_data = {}

    with patch("singulr.bot.security_wizard.is_channel_admin", new_callable=AsyncMock, return_value=False):
        result = await security_command(update, context)

    assert result == -1
    update.message.reply_text.assert_awaited_once()
    assert "administrator" in update.message.reply_text.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_wizard_state_transitions_to_confirm() -> None:
    """Preset → evasion → ops → confirm flow advances conversation state."""
    context = MagicMock()
    context.user_data = {WIZARD_CHANNEL_KEY: 100, WIZARD_PRESET_KEY: "balanced"}

    preset_update = _callback_update("sec_preset_balanced")
    with patch("singulr.bot.security_wizard.is_channel_admin", new_callable=AsyncMock, return_value=True):
        pass
    state = await preset_selected(preset_update, context)
    assert state == WizardState.EVASION

    context.user_data[WIZARD_PRESET_KEY] = "balanced"
    evasion_update = _callback_update("sec_evasion_flag_medium")
    state = await evasion_selected(evasion_update, context)
    assert state == WizardState.OPS_CHAT

    context.user_data[WIZARD_EVASION_KEY] = "flag_medium"
    ops_update = _callback_update("sec_ops_skip")
    with patch("singulr.bot.security_wizard.get_settings") as mock_settings:
        mock_settings.return_value.admin_ops_chat_id = 0
        mock_settings.return_value.log_channel_id = 0
        state = await ops_selected(ops_update, context)
    assert state == WizardState.CONFIRM
    ops_update.callback_query.edit_message_text.assert_awaited()


@pytest.mark.asyncio
async def test_upsert_persists_wizard_completed_at(db_session: AsyncSession) -> None:
    """Confirm path persists settings with wizard_completed_at."""
    row = await upsert_channel_security_settings(
        db_session,
        channel_id=88001,
        preset="strict",
        evasion_mode="review_most",
        admin_ops_chat_id=-100555,
    )

    assert row.security_preset == "strict"
    assert row.wizard_completed_at is not None
    assert row.admin_ops_chat_id == -100555
    resolved = resolve_wizard_thresholds("strict", "review_most")
    assert row.ban_evasion_auto_deny_threshold == resolved.ban_evasion_auto_deny_threshold


@pytest.mark.asyncio
async def test_rerun_security_updates_existing_row(db_session: AsyncSession) -> None:
    """Re-running the wizard updates the same channel row."""
    await upsert_channel_security_settings(
        db_session,
        channel_id=88002,
        preset="open",
        evasion_mode="high_only",
        admin_ops_chat_id=None,
    )
    await upsert_channel_security_settings(
        db_session,
        channel_id=88002,
        preset="strict",
        evasion_mode="flag_medium",
        admin_ops_chat_id=-100777,
    )

    row = await db_session.scalar(
        select(ChannelSecuritySettings).where(ChannelSecuritySettings.channel_id == 88002)
    )
    assert row is not None
    assert row.security_preset == "strict"
    assert row.admin_ops_chat_id == -100777


@pytest.mark.asyncio
async def test_confirm_persists_settings(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """Confirm callback writes ChannelSecuritySettings."""
    context = MagicMock()
    context.user_data = {
        WIZARD_CHANNEL_KEY: 88003,
        WIZARD_PRESET_KEY: "balanced",
        WIZARD_EVASION_KEY: "high_only",
        WIZARD_OPS_KEY: -100999,
    }
    update = _callback_update("sec_confirm_yes")

    with patch("singulr.bot.security_wizard.SessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await confirm_selected(update, context)

    assert result == -1
    row = await db_session.scalar(
        select(ChannelSecuritySettings).where(ChannelSecuritySettings.channel_id == 88003)
    )
    assert row is not None
    assert row.security_preset == "balanced"
    assert row.wizard_completed_at is not None
