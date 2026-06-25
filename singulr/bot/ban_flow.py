"""Inline keyboard flow for admin ban category and severity selection."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from singulr.domain.ban_taxonomy import BanCategory, BanSeverity

PENDING_BAN_USER_KEY = "pending_ban_user_id"
PENDING_BAN_CATEGORY_KEY = "pending_ban_category"


def category_keyboard() -> InlineKeyboardMarkup:
    """Build category picker buttons (callback: ban_cat_<value>)."""
    rows: list[list[InlineKeyboardButton]] = []
    categories = list(BanCategory)
    for index in range(0, len(categories), 2):
        pair = categories[index : index + 2]
        rows.append(
            [
                InlineKeyboardButton(
                    cat.value.replace("_", " ").title(),
                    callback_data=f"ban_cat_{cat.value}",
                )
                for cat in pair
            ]
        )
    return InlineKeyboardMarkup(rows)


def severity_keyboard() -> InlineKeyboardMarkup:
    """Build severity picker buttons (callback: ban_sev_<value>)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(sev.value.title(), callback_data=f"ban_sev_{sev.value}")
                for sev in BanSeverity
            ]
        ]
    )


def parse_ban_category(callback_data: str) -> BanCategory | None:
    """Parse ban_cat_<category> callback payload."""
    if not callback_data.startswith("ban_cat_"):
        return None
    value = callback_data.removeprefix("ban_cat_")
    try:
        return BanCategory(value)
    except ValueError:
        return None


def parse_ban_severity(callback_data: str) -> BanSeverity | None:
    """Parse ban_sev_<severity> callback payload."""
    if not callback_data.startswith("ban_sev_"):
        return None
    value = callback_data.removeprefix("ban_sev_")
    try:
        return BanSeverity(value)
    except ValueError:
        return None


def parse_ban_user_id(callback_data: str) -> int | None:
    """Parse ban_<user_id> start-step callback payload."""
    if not callback_data.startswith("ban_"):
        return None
    if callback_data.startswith("ban_cat_") or callback_data.startswith("ban_sev_"):
        return None
    suffix = callback_data.removeprefix("ban_")
    if not suffix.isdigit():
        return None
    return int(suffix)
