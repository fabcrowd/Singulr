"""Tests for admin ban inline keyboard parsers."""

from __future__ import annotations

from singulr.bot.ban_flow import parse_ban_category, parse_ban_severity, parse_ban_user_id
from singulr.domain.ban_taxonomy import BanCategory, BanSeverity


def test_parse_ban_category_accepts_valid_callbacks() -> None:
    """Category callbacks map to BanCategory enum values."""
    assert parse_ban_category("ban_cat_scam_fraud") == BanCategory.SCAM_FRAUD
    assert parse_ban_category("ban_cat_bot_abuse") == BanCategory.BOT_ABUSE


def test_parse_ban_category_rejects_malformed_callbacks() -> None:
    """Unknown categories and wrong prefixes return None."""
    assert parse_ban_category("ban_cat_not_a_category") is None
    assert parse_ban_category("ban_12345") is None
    assert parse_ban_category("approve_1") is None


def test_parse_ban_severity_accepts_valid_callbacks() -> None:
    """Severity callbacks map to BanSeverity enum values."""
    assert parse_ban_severity("ban_sev_high") == BanSeverity.HIGH
    assert parse_ban_severity("ban_sev_permanent") == BanSeverity.PERMANENT


def test_parse_ban_severity_rejects_malformed_callbacks() -> None:
    """Unknown severities return None."""
    assert parse_ban_severity("ban_sev_critical") is None
    assert parse_ban_severity("ban_cat_spam") is None


def test_parse_ban_user_id_accepts_numeric_suffix() -> None:
    """Ban start callbacks encode the target user id."""
    assert parse_ban_user_id("ban_12345") == 12345


def test_parse_ban_user_id_rejects_category_and_severity_callbacks() -> None:
    """Category and severity callbacks are not mistaken for user ids."""
    assert parse_ban_user_id("ban_cat_spam") is None
    assert parse_ban_user_id("ban_sev_low") is None
    assert parse_ban_user_id("ban_notanumber") is None
