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
    WIZARD_INSTANT_BAN_KEY,
    WIZARD_NET_CATEGORIES_KEY,
    WIZARD_NETWORK_MODE_KEY,
    WIZARD_OPS_KEY,
    WIZARD_PRESET_KEY,
    WIZARD_SOCIAL_EXTERNAL_KEY,
    WIZARD_SOCIAL_PROFILING_KEY,
    WIZARD_AUTOMATION_MODE_KEY,
    WIZARD_AI_THRESHOLD_KEY,
    WizardState,
    automation_selected,
    confirm_selected,
    delta_selected,
    evasion_selected,
    instant_ban_selected,
    network_categories_selected,
    network_mode_selected,
    ops_selected,
    preset_selected,
    security_command,
    security_cancel,
    social_selected,
)
from singulr.config import get_settings
from singulr.models import ChannelSecuritySettings
from singulr.services.channel_policy import resolve_wizard_thresholds, upsert_channel_security_settings


@pytest.fixture(autouse=True)
def _wizard_channel_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Callback handlers require channel admin unless a test overrides this."""
    monkeypatch.setattr(
        "singulr.bot.security_wizard.is_channel_admin",
        AsyncMock(return_value=True),
    )


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
    """Preset through social settings reaches confirm."""
    context = MagicMock()
    context.user_data = {WIZARD_CHANNEL_KEY: 100, WIZARD_PRESET_KEY: "balanced"}

    preset_update = _callback_update("sec_preset_balanced")
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
    assert state == WizardState.NETWORK_MODE

    context.user_data[WIZARD_OPS_KEY] = None
    net_update = _callback_update("sec_net_read_write")
    state = await network_mode_selected(net_update, context)
    assert state == WizardState.NETWORK_CATEGORIES
    assert context.user_data[WIZARD_NETWORK_MODE_KEY] == "read_write"

    context.user_data[WIZARD_NET_CATEGORIES_KEY] = {"scam_fraud", "spam"}
    cat_update = _callback_update("sec_cat_done")
    state = await network_categories_selected(cat_update, context)
    assert state == WizardState.INSTANT_BAN

    ib_update = _callback_update("sec_ib_done")
    state = await instant_ban_selected(ib_update, context)
    assert state == WizardState.SOCIAL

    soc_update = _callback_update("sec_soc_done")
    state = await social_selected(soc_update, context)
    assert state == WizardState.AUTOMATION

    auto_update = _callback_update("sec_auto_pending")
    state = await automation_selected(auto_update, context)
    assert state == WizardState.CONFIRM
    auto_update.callback_query.edit_message_text.assert_awaited()
    summary = auto_update.callback_query.edit_message_text.await_args.args[0]
    assert "read_write" in summary
    assert "scam_fraud" in summary
    assert "Social profiling" in summary
    assert "Automation handling: pending" in summary


@pytest.mark.asyncio
async def test_upsert_persists_wizard_completed_at(db_session: AsyncSession) -> None:
    """Confirm path persists settings with wizard_completed_at."""
    row = await upsert_channel_security_settings(
        db_session,
        channel_id=88001,
        preset="strict",
        evasion_mode="review_most",
        admin_ops_chat_id=-100555,
        network_registry_mode="read_write",
        network_auto_reject_categories=["scam_fraud", "raid_coordination"],
    )

    assert row.security_preset == "strict"
    assert row.wizard_completed_at is not None
    assert row.wizard_version == 4
    assert row.network_registry_mode == "read_write"
    assert row.share_bans_to_network is True
    assert row.network_auto_reject_categories == ["scam_fraud", "raid_coordination"]
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
        WIZARD_NETWORK_MODE_KEY: "read",
        WIZARD_NET_CATEGORIES_KEY: {"harassment", "scam_fraud"},
        WIZARD_INSTANT_BAN_KEY: {"impersonation", "bot_abuse"},
        WIZARD_SOCIAL_PROFILING_KEY: True,
        WIZARD_SOCIAL_EXTERNAL_KEY: False,
        WIZARD_AUTOMATION_MODE_KEY: "flag",
        WIZARD_AI_THRESHOLD_KEY: 50,
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
    assert row.wizard_version == 4
    assert row.network_registry_mode == "read"
    assert set(row.network_auto_reject_categories or []) == {"harassment", "scam_fraud"}


@pytest.mark.asyncio
async def test_confirm_rejects_non_admin(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-admin cannot persist security settings via confirm callback."""
    monkeypatch.setattr(
        "singulr.bot.security_wizard.is_channel_admin",
        AsyncMock(return_value=False),
    )
    context = MagicMock()
    context.user_data = {
        WIZARD_CHANNEL_KEY: 88004,
        WIZARD_PRESET_KEY: "balanced",
        WIZARD_EVASION_KEY: "high_only",
        WIZARD_OPS_KEY: None,
        WIZARD_NETWORK_MODE_KEY: "read",
        WIZARD_NET_CATEGORIES_KEY: set(),
        WIZARD_INSTANT_BAN_KEY: set(),
        WIZARD_SOCIAL_PROFILING_KEY: True,
        WIZARD_SOCIAL_EXTERNAL_KEY: False,
        WIZARD_AUTOMATION_MODE_KEY: "flag",
        WIZARD_AI_THRESHOLD_KEY: 50,
    }
    update = _callback_update("sec_confirm_yes")
    update.callback_query.message = MagicMock()
    update.callback_query.message.reply_text = AsyncMock()

    with patch("singulr.bot.security_wizard.SessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await confirm_selected(update, context)

    assert result == -1
    row = await db_session.scalar(
        select(ChannelSecuritySettings).where(ChannelSecuritySettings.channel_id == 88004)
    )
    assert row is None
    update.callback_query.message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_category_toggle_updates_selection() -> None:
    """Tapping a category chip toggles membership in the selection set."""
    context = MagicMock()
    context.user_data = {
        WIZARD_CHANNEL_KEY: 100,
        WIZARD_PRESET_KEY: "balanced",
        WIZARD_EVASION_KEY: "high_only",
        WIZARD_OPS_KEY: None,
        WIZARD_NETWORK_MODE_KEY: "read",
        WIZARD_NET_CATEGORIES_KEY: {"scam_fraud"},
    }
    update = _callback_update("sec_cat_spam")
    state = await network_categories_selected(update, context)
    assert state == WizardState.NETWORK_CATEGORIES
    assert context.user_data[WIZARD_NET_CATEGORIES_KEY] == {"scam_fraud", "spam"}


@pytest.mark.asyncio
async def test_delta_prompt_when_wizard_version_one(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Admins on wizard v1 see delta upgrade prompt on /security."""
    from datetime import UTC, datetime

    monkeypatch.setenv("CHANNEL_ID", "88010")
    get_settings.cache_clear()
    row = await upsert_channel_security_settings(
        db_session,
        channel_id=88010,
        preset="balanced",
        evasion_mode="high_only",
        admin_ops_chat_id=None,
    )
    row.wizard_version = 1
    row.wizard_completed_at = datetime.now(UTC)
    await db_session.commit()

    update = _private_update()
    context = MagicMock()
    context.user_data = {}

    with patch("singulr.bot.security_wizard.is_channel_admin", new_callable=AsyncMock, return_value=True):
        with patch("singulr.bot.security_wizard.SessionLocal") as session_local:
            session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
            session_local.return_value.__aexit__ = AsyncMock(return_value=False)
            state = await security_command(update, context)

    assert state == WizardState.DELTA
    text = update.message.reply_text.await_args.args[0]
    assert "automation" in text.lower()


@pytest.mark.asyncio
async def test_delta_new_skips_to_instant_ban(db_session: AsyncSession) -> None:
    """Delta path jumps to new social profiling questions only."""
    from datetime import UTC, datetime

    row = ChannelSecuritySettings(
        channel_id=88011,
        security_preset="open",
        ban_evasion_auto_deny_threshold=0.95,
        local_similarity_flag_threshold=0.90,
        network_registry_mode="off",
        wizard_completed_at=datetime.now(UTC),
        wizard_version=1,
    )
    db_session.add(row)
    await db_session.commit()

    context = MagicMock()
    context.user_data = {WIZARD_CHANNEL_KEY: 88011}
    update = _callback_update("sec_delta_new")

    with patch("singulr.bot.security_wizard.SessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        state = await delta_selected(update, context)

    assert state == WizardState.INSTANT_BAN
    assert context.user_data[WIZARD_PRESET_KEY] == "open"


@pytest.mark.asyncio
async def test_delta_v3_jumps_to_automation_step(db_session: AsyncSession) -> None:
    """Wizard v3 admins answer only the new automation question."""
    from datetime import UTC, datetime

    row = ChannelSecuritySettings(
        channel_id=88012,
        security_preset="balanced",
        ban_evasion_auto_deny_threshold=0.92,
        local_similarity_flag_threshold=0.85,
        network_registry_mode="read",
        wizard_completed_at=datetime.now(UTC),
        wizard_version=3,
    )
    db_session.add(row)
    await db_session.commit()

    context = MagicMock()
    context.user_data = {WIZARD_CHANNEL_KEY: 88012}
    update = _callback_update("sec_delta_new")

    with patch("singulr.bot.security_wizard.SessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        state = await delta_selected(update, context)

    assert state == WizardState.AUTOMATION
    assert context.user_data[WIZARD_PRESET_KEY] == "balanced"


@pytest.mark.asyncio
async def test_security_cancel_does_not_persist_partial_policy(
    db_session: AsyncSession,
) -> None:
    """Cancel command exits without writing channel security settings."""
    channel_id = 88060
    update = _private_update()
    context = MagicMock()
    context.user_data = {
        WIZARD_CHANNEL_KEY: channel_id,
        WIZARD_PRESET_KEY: "strict",
        WIZARD_EVASION_KEY: "high_only",
    }

    result = await security_cancel(update, context)

    assert result == -1
    row = await db_session.get(ChannelSecuritySettings, channel_id)
    assert row is None
    assert WIZARD_CHANNEL_KEY not in context.user_data


@pytest.mark.asyncio
async def test_confirm_restart_does_not_persist_partial_policy(
    db_session: AsyncSession,
) -> None:
    """Start over from confirm keeps the previously saved policy unchanged."""
    channel_id = 88061
    await upsert_channel_security_settings(
        db_session,
        channel_id=channel_id,
        preset="balanced",
        evasion_mode="high_only",
        admin_ops_chat_id=None,
    )
    await db_session.commit()

    context = MagicMock()
    context.user_data = {
        WIZARD_CHANNEL_KEY: channel_id,
        WIZARD_PRESET_KEY: "strict",
        WIZARD_EVASION_KEY: "review_most",
        WIZARD_OPS_KEY: None,
        WIZARD_NETWORK_MODE_KEY: "off",
        WIZARD_NET_CATEGORIES_KEY: set(),
        WIZARD_INSTANT_BAN_KEY: set(),
        WIZARD_SOCIAL_PROFILING_KEY: True,
        WIZARD_SOCIAL_EXTERNAL_KEY: False,
        WIZARD_AUTOMATION_MODE_KEY: "flag",
        WIZARD_AI_THRESHOLD_KEY: 50,
    }
    update = _callback_update("sec_confirm_restart")

    with patch("singulr.bot.security_wizard.SessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        state = await confirm_selected(update, context)

    assert state == WizardState.PRESET
    row = await db_session.get(ChannelSecuritySettings, channel_id)
    assert row is not None
    assert row.security_preset == "balanced"
