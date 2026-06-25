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
from singulr.domain.ban_taxonomy import BanCategory
from singulr.models import ChannelSecuritySettings
from singulr.services.channel_policy import (
    DEFAULT_NETWORK_AUTO_REJECT,
    format_policy_summary,
    resolve_wizard_thresholds,
    upsert_channel_security_settings,
)

logger = logging.getLogger(__name__)

WIZARD_CHANNEL_KEY = "security_wizard_channel_id"
WIZARD_PRESET_KEY = "security_wizard_preset"
WIZARD_EVASION_KEY = "security_wizard_evasion"
WIZARD_OPS_KEY = "security_wizard_ops_chat_id"
WIZARD_NETWORK_MODE_KEY = "security_wizard_network_mode"
WIZARD_NET_CATEGORIES_KEY = "security_wizard_net_categories"
WIZARD_DELTA_ONLY_KEY = "security_wizard_delta_only"

CURRENT_WIZARD_VERSION = 2


class WizardState(IntEnum):
    """Conversation states for the security wizard."""

    DELTA = 0
    PRESET = 1
    EVASION = 2
    OPS_CHAT = 3
    NETWORK_MODE = 4
    NETWORK_CATEGORIES = 5
    CONFIRM = 6


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


def _network_mode_keyboard() -> InlineKeyboardMarkup:
    """Network registry participation keyboard."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("A — Off (local only)", callback_data="sec_net_off")],
            [InlineKeyboardButton("B — Read network bans", callback_data="sec_net_read")],
            [
                InlineKeyboardButton(
                    "C — Read + share our bans",
                    callback_data="sec_net_read_write",
                )
            ],
        ]
    )


def _categories_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    """Multi-select ban categories for network auto-reject."""
    rows: list[list[InlineKeyboardButton]] = []
    for category in BanCategory:
        mark = "✓ " if category.value in selected else ""
        rows.append(
            [
                InlineKeyboardButton(
                    f"{mark}{category.value}",
                    callback_data=f"sec_cat_{category.value}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("Use defaults", callback_data="sec_cat_defaults"),
            InlineKeyboardButton("Done", callback_data="sec_cat_done"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def _delta_keyboard() -> InlineKeyboardMarkup:
    """Upgrade prompt for admins on wizard_version < 2."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Answer new questions only",
                    callback_data="sec_delta_new",
                ),
                InlineKeyboardButton("Review all settings", callback_data="sec_delta_full"),
            ],
        ]
    )


def _wizard_user_data_keys() -> tuple[str, ...]:
    return (
        WIZARD_CHANNEL_KEY,
        WIZARD_PRESET_KEY,
        WIZARD_EVASION_KEY,
        WIZARD_OPS_KEY,
        WIZARD_NETWORK_MODE_KEY,
        WIZARD_NET_CATEGORIES_KEY,
        WIZARD_DELTA_ONLY_KEY,
    )


def _clear_wizard_user_data(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in _wizard_user_data_keys():
        context.user_data.pop(key, None)


def _preview_settings(context: ContextTypes.DEFAULT_TYPE) -> ChannelSecuritySettings:
    """Build a preview row from in-progress wizard answers."""
    channel_id = int(context.user_data[WIZARD_CHANNEL_KEY])
    preset = str(context.user_data[WIZARD_PRESET_KEY])
    evasion = str(context.user_data[WIZARD_EVASION_KEY])
    ops_chat_id = context.user_data.get(WIZARD_OPS_KEY)
    network_mode = str(
        context.user_data.get(WIZARD_NETWORK_MODE_KEY, resolve_wizard_thresholds(preset, evasion).network_registry_mode)
    )
    categories = sorted(context.user_data.get(WIZARD_NET_CATEGORIES_KEY, set(DEFAULT_NETWORK_AUTO_REJECT)))
    resolved = resolve_wizard_thresholds(preset, evasion)
    return ChannelSecuritySettings(
        channel_id=channel_id,
        security_preset=resolved.security_preset,
        ban_evasion_auto_deny_threshold=resolved.ban_evasion_auto_deny_threshold,
        local_similarity_flag_threshold=resolved.local_similarity_flag_threshold,
        network_registry_mode=network_mode,
        share_bans_to_network=network_mode == "read_write",
        network_auto_reject_categories=categories,
        admin_ops_chat_id=ops_chat_id,
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

    channel_id = settings.channel_id
    context.user_data[WIZARD_CHANNEL_KEY] = channel_id

    async with SessionLocal() as session:
        existing = await session.get(ChannelSecuritySettings, channel_id)

    if (
        existing is not None
        and existing.wizard_completed_at is not None
        and existing.wizard_version < CURRENT_WIZARD_VERSION
    ):
        await update.message.reply_text(
            "New network registry settings are available.\n"
            "Answer only the new questions, or review everything from scratch:",
            reply_markup=_delta_keyboard(),
        )
        return WizardState.DELTA

    await update.message.reply_text(
        "Security setup (question 1 of 5)\nChoose a preset:",
        reply_markup=_preset_keyboard(),
    )
    return WizardState.PRESET


async def delta_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle delta upgrade choice for wizard_version < 2."""
    query = update.callback_query
    if not query or not query.data:
        return ConversationHandler.END
    await query.answer()

    channel_id = int(context.user_data[WIZARD_CHANNEL_KEY])
    if query.data == "sec_delta_full":
        await query.edit_message_text(
            "Security setup (question 1 of 5)\nChoose a preset:",
            reply_markup=_preset_keyboard(),
        )
        return WizardState.PRESET

    async with SessionLocal() as session:
        existing = await session.get(ChannelSecuritySettings, channel_id)
    if existing is None:
        await query.edit_message_text(
            "Security setup (question 1 of 5)\nChoose a preset:",
            reply_markup=_preset_keyboard(),
        )
        return WizardState.PRESET

    context.user_data[WIZARD_DELTA_ONLY_KEY] = True
    context.user_data[WIZARD_PRESET_KEY] = existing.security_preset
    context.user_data[WIZARD_EVASION_KEY] = _evasion_mode_from_row(existing)
    context.user_data[WIZARD_OPS_KEY] = existing.admin_ops_chat_id
    await query.edit_message_text(
        "Security setup (question 4 of 5)\nNetwork registry participation:",
        reply_markup=_network_mode_keyboard(),
    )
    return WizardState.NETWORK_MODE


def _evasion_mode_from_row(row: ChannelSecuritySettings) -> str:
    """Best-effort evasion mode label from stored thresholds."""
    preset_bundle = resolve_wizard_thresholds(row.security_preset, "high_only")
    if row.ban_evasion_auto_deny_threshold is None:
        return "high_only"
    delta = row.ban_evasion_auto_deny_threshold - preset_bundle.ban_evasion_auto_deny_threshold
    if delta <= -0.03:
        return "review_most"
    if delta <= -0.01:
        return "flag_medium"
    return "high_only"


async def preset_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle preset callback."""
    query = update.callback_query
    if not query or not query.data:
        return ConversationHandler.END
    await query.answer()
    preset = query.data.removeprefix("sec_preset_")
    context.user_data[WIZARD_PRESET_KEY] = preset
    await query.edit_message_text(
        "Security setup (question 2 of 5)\nBan evasion strictness:",
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
        "Security setup (question 3 of 5)\nWhere should pending reviews be sent?",
        reply_markup=_ops_keyboard(),
    )
    return WizardState.OPS_CHAT


async def ops_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle ops chat selection and advance to network registry."""
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

    await query.edit_message_text(
        "Security setup (question 4 of 5)\nNetwork registry participation:",
        reply_markup=_network_mode_keyboard(),
    )
    return WizardState.NETWORK_MODE


async def network_mode_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle network registry mode selection."""
    query = update.callback_query
    if not query or not query.data:
        return ConversationHandler.END
    await query.answer()
    mode = query.data.removeprefix("sec_net_")
    context.user_data[WIZARD_NETWORK_MODE_KEY] = mode
    context.user_data[WIZARD_NET_CATEGORIES_KEY] = set(DEFAULT_NETWORK_AUTO_REJECT)
    await query.edit_message_text(
        "Security setup (question 5 of 5)\n"
        "Tap categories to auto-reject from the network (toggle on/off), then Done:",
        reply_markup=_categories_keyboard(set(DEFAULT_NETWORK_AUTO_REJECT)),
    )
    return WizardState.NETWORK_CATEGORIES


async def network_categories_selected(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Toggle network auto-reject categories or finish selection."""
    query = update.callback_query
    if not query or not query.data:
        return ConversationHandler.END
    await query.answer()

    selected: set[str] = set(context.user_data.get(WIZARD_NET_CATEGORIES_KEY, set()))

    if query.data == "sec_cat_defaults":
        selected = set(DEFAULT_NETWORK_AUTO_REJECT)
        context.user_data[WIZARD_NET_CATEGORIES_KEY] = selected
        await query.edit_message_text(
            "Security setup (question 5 of 5)\n"
            "Tap categories to auto-reject from the network (toggle on/off), then Done:",
            reply_markup=_categories_keyboard(selected),
        )
        return WizardState.NETWORK_CATEGORIES

    if query.data == "sec_cat_done":
        if not selected:
            selected = set(DEFAULT_NETWORK_AUTO_REJECT)
            context.user_data[WIZARD_NET_CATEGORIES_KEY] = selected
        preview = _preview_settings(context)
        summary = format_policy_summary(preview)
        channel_id = int(context.user_data[WIZARD_CHANNEL_KEY])
        await query.edit_message_text(
            f"Confirm security settings for channel {channel_id}:\n\n{summary}",
            reply_markup=_confirm_keyboard(),
        )
        return WizardState.CONFIRM

    category = query.data.removeprefix("sec_cat_")
    if category in selected:
        selected.remove(category)
    else:
        selected.add(category)
    context.user_data[WIZARD_NET_CATEGORIES_KEY] = selected
    await query.edit_message_text(
        "Security setup (question 5 of 5)\n"
        "Tap categories to auto-reject from the network (toggle on/off), then Done:",
        reply_markup=_categories_keyboard(selected),
    )
    return WizardState.NETWORK_CATEGORIES


async def confirm_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirm or restart the wizard."""
    query = update.callback_query
    if not query or not query.data:
        return ConversationHandler.END
    await query.answer()
    if query.data == "sec_confirm_restart":
        channel_id = int(context.user_data[WIZARD_CHANNEL_KEY])
        _clear_wizard_user_data(context)
        context.user_data[WIZARD_CHANNEL_KEY] = channel_id
        await query.edit_message_text(
            "Security setup (question 1 of 5)\nChoose a preset:",
            reply_markup=_preset_keyboard(),
        )
        return WizardState.PRESET

    channel_id = int(context.user_data[WIZARD_CHANNEL_KEY])
    preset = str(context.user_data[WIZARD_PRESET_KEY])
    evasion = str(context.user_data[WIZARD_EVASION_KEY])
    ops_chat_id = context.user_data.get(WIZARD_OPS_KEY)
    network_mode = str(context.user_data[WIZARD_NETWORK_MODE_KEY])
    categories = sorted(context.user_data.get(WIZARD_NET_CATEGORIES_KEY, set()))

    async with SessionLocal() as session:
        await upsert_channel_security_settings(
            session,
            channel_id=channel_id,
            preset=preset,
            evasion_mode=evasion,
            admin_ops_chat_id=ops_chat_id,
            network_registry_mode=network_mode,
            network_auto_reject_categories=categories,
        )

    await query.edit_message_text("Security settings saved. New join verifications will use this policy.")
    _clear_wizard_user_data(context)
    return ConversationHandler.END


async def security_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the wizard."""
    if update.message:
        await update.message.reply_text("Security setup cancelled.")
    _clear_wizard_user_data(context)
    return ConversationHandler.END


def build_security_wizard_handler() -> ConversationHandler:
    """Register the /security ConversationHandler."""
    return ConversationHandler(
        entry_points=[CommandHandler("security", security_command)],
        states={
            WizardState.DELTA: [
                CallbackQueryHandler(delta_selected, pattern=r"^sec_delta_"),
            ],
            WizardState.PRESET: [
                CallbackQueryHandler(preset_selected, pattern=r"^sec_preset_"),
            ],
            WizardState.EVASION: [
                CallbackQueryHandler(evasion_selected, pattern=r"^sec_evasion_"),
            ],
            WizardState.OPS_CHAT: [
                CallbackQueryHandler(ops_selected, pattern=r"^sec_ops_"),
            ],
            WizardState.NETWORK_MODE: [
                CallbackQueryHandler(network_mode_selected, pattern=r"^sec_net_"),
            ],
            WizardState.NETWORK_CATEGORIES: [
                CallbackQueryHandler(network_categories_selected, pattern=r"^sec_cat_"),
            ],
            WizardState.CONFIRM: [
                CallbackQueryHandler(confirm_selected, pattern=r"^sec_confirm_"),
            ],
        },
        fallbacks=[CommandHandler("cancel", security_cancel)],
        name="security_wizard",
        persistent=False,
    )
