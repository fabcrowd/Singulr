"""Private DM security setup wizard (/security)."""

from __future__ import annotations

import logging
from enum import IntEnum

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
)

from singulr.config import get_settings
from singulr.db import SessionLocal
from singulr.models import ChannelSecuritySettings
from singulr.services.channel_policy import (
    format_policy_summary,
    resolve_wizard_thresholds,
    upsert_channel_security_settings,
)

logger = logging.getLogger(__name__)

WIZARD_CHANNEL_KEY = "security_wizard_channel_id"
WIZARD_PRESET_KEY = "security_wizard_preset"
WIZARD_EVASION_KEY = "security_wizard_evasion"
WIZARD_OPS_KEY = "security_wizard_ops_chat_id"


class WizardState(IntEnum):
    """Conversation states for the security wizard."""

    PRESET = 1
    EVASION = 2
    OPS_CHAT = 3
    CONFIRM = 4


async def is_channel_admin(update: Update, channel_id: int) -> bool:
    """Return True when the user is an administrator of the target channel."""
    user = update.effective_user
    if not user or not update.effective_chat:
        return False
    try:
        member = await update.get_bot().get_chat_member(channel_id, user.id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_chat_member failed for %s: %s", channel_id, exc)
        return False
    return member.status in {"administrator", "creator"}


def _preset_keyboard() -> InlineKeyboardMarkup:
    """Preset selection keyboard."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("A — Open", callback_data="sec_preset_open"),
                InlineKeyboardButton("B — Balanced", callback_data="sec_preset_balanced"),
            ],
            [InlineKeyboardButton("C — Strict", callback_data="sec_preset_strict")],
        ]
    )


def _evasion_keyboard() -> InlineKeyboardMarkup:
    """Ban-evasion strictness keyboard."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("A — Auto-deny high matches only", callback_data="sec_evasion_high_only")],
            [InlineKeyboardButton("B — Also flag medium matches", callback_data="sec_evasion_flag_medium")],
            [InlineKeyboardButton("C — Review almost everything", callback_data="sec_evasion_review_most")],
        ]
    )


def _ops_keyboard() -> InlineKeyboardMarkup:
    """Admin ops chat selection keyboard."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("A — Use default ops chat", callback_data="sec_ops_default"),
                InlineKeyboardButton("B — Skip ops chat", callback_data="sec_ops_skip"),
            ],
        ]
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirm or restart keyboard."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirm", callback_data="sec_confirm_yes"),
                InlineKeyboardButton("Start over", callback_data="sec_confirm_restart"),
            ],
        ]
    )


async def security_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start /security wizard in a private chat."""
    if not update.message or not update.effective_chat:
        return ConversationHandler.END
    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Open a private chat with me and run /security again.")
        return ConversationHandler.END

    settings = get_settings()
    if not settings.channel_id:
        await update.message.reply_text("Singulr channel is not configured yet.")
        return ConversationHandler.END

    if not await is_channel_admin(update, settings.channel_id):
        await update.message.reply_text("Only channel administrators can configure security.")
        return ConversationHandler.END

    context.user_data[WIZARD_CHANNEL_KEY] = settings.channel_id
    await update.message.reply_text(
        "Security setup (question 1 of 3)\nChoose a preset:",
        reply_markup=_preset_keyboard(),
    )
    return WizardState.PRESET


async def preset_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle preset callback."""
    query = update.callback_query
    if not query or not query.data:
        return ConversationHandler.END
    await query.answer()
    preset = query.data.removeprefix("sec_preset_")
    context.user_data[WIZARD_PRESET_KEY] = preset
    await query.edit_message_text(
        "Security setup (question 2 of 3)\nBan evasion strictness:",
        reply_markup=_evasion_keyboard(),
    )
    return WizardState.EVASION


async def evasion_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle evasion strictness callback."""
    query = update.callback_query
    if not query or not query.data:
        return ConversationHandler.END
    await query.answer()
    evasion = query.data.removeprefix("sec_evasion_")
    context.user_data[WIZARD_EVASION_KEY] = evasion
    await query.edit_message_text(
        "Security setup (question 3 of 3)\nWhere should pending reviews be sent?",
        reply_markup=_ops_keyboard(),
    )
    return WizardState.OPS_CHAT


async def ops_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle ops chat selection and show summary."""
    query = update.callback_query
    if not query or not query.data:
        return ConversationHandler.END
    await query.answer()
    settings = get_settings()
    if query.data == "sec_ops_default":
        ops_chat_id = settings.admin_ops_chat_id or settings.log_channel_id or None
    else:
        ops_chat_id = None
    context.user_data[WIZARD_OPS_KEY] = ops_chat_id

    channel_id = int(context.user_data[WIZARD_CHANNEL_KEY])
    preset = str(context.user_data[WIZARD_PRESET_KEY])
    evasion = str(context.user_data[WIZARD_EVASION_KEY])
    resolved = resolve_wizard_thresholds(preset, evasion)
    preview = ChannelSecuritySettings(
        channel_id=channel_id,
        security_preset=resolved.security_preset,
        ban_evasion_auto_deny_threshold=resolved.ban_evasion_auto_deny_threshold,
        local_similarity_flag_threshold=resolved.local_similarity_flag_threshold,
        network_registry_mode=resolved.network_registry_mode,
        admin_ops_chat_id=ops_chat_id,
    )
    summary = format_policy_summary(preview)

    await query.edit_message_text(
        f"Confirm security settings for channel {channel_id}:\n\n{summary}",
        reply_markup=_confirm_keyboard(),
    )
    return WizardState.CONFIRM


async def confirm_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirm or restart the wizard."""
    query = update.callback_query
    if not query or not query.data:
        return ConversationHandler.END
    await query.answer()
    if query.data == "sec_confirm_restart":
        context.user_data.pop(WIZARD_PRESET_KEY, None)
        context.user_data.pop(WIZARD_EVASION_KEY, None)
        context.user_data.pop(WIZARD_OPS_KEY, None)
        await query.edit_message_text(
            "Security setup (question 1 of 3)\nChoose a preset:",
            reply_markup=_preset_keyboard(),
        )
        return WizardState.PRESET

    channel_id = int(context.user_data[WIZARD_CHANNEL_KEY])
    preset = str(context.user_data[WIZARD_PRESET_KEY])
    evasion = str(context.user_data[WIZARD_EVASION_KEY])
    ops_chat_id = context.user_data.get(WIZARD_OPS_KEY)

    async with SessionLocal() as session:
        await upsert_channel_security_settings(
            session,
            channel_id=channel_id,
            preset=preset,
            evasion_mode=evasion,
            admin_ops_chat_id=ops_chat_id,
        )

    await query.edit_message_text("Security settings saved. New join verifications will use this policy.")
    for key in (WIZARD_CHANNEL_KEY, WIZARD_PRESET_KEY, WIZARD_EVASION_KEY, WIZARD_OPS_KEY):
        context.user_data.pop(key, None)
    return ConversationHandler.END


async def security_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the wizard."""
    if update.message:
        await update.message.reply_text("Security setup cancelled.")
    for key in (WIZARD_CHANNEL_KEY, WIZARD_PRESET_KEY, WIZARD_EVASION_KEY, WIZARD_OPS_KEY):
        context.user_data.pop(key, None)
    return ConversationHandler.END


def build_security_wizard_handler() -> ConversationHandler:
    """Register the /security ConversationHandler."""
    return ConversationHandler(
        entry_points=[CommandHandler("security", security_command)],
        states={
            WizardState.PRESET: [
                CallbackQueryHandler(preset_selected, pattern=r"^sec_preset_"),
            ],
            WizardState.EVASION: [
                CallbackQueryHandler(evasion_selected, pattern=r"^sec_evasion_"),
            ],
            WizardState.OPS_CHAT: [
                CallbackQueryHandler(ops_selected, pattern=r"^sec_ops_"),
            ],
            WizardState.CONFIRM: [
                CallbackQueryHandler(confirm_selected, pattern=r"^sec_confirm_"),
            ],
        },
        fallbacks=[CommandHandler("cancel", security_cancel)],
        name="security_wizard",
        persistent=False,
    )
