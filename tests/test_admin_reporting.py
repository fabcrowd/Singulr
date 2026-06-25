"""Tests for ban history formatting and admin reporting."""

from __future__ import annotations

from datetime import UTC, datetime

from singulr.models import Ban
from singulr.services.ban_history import format_ban_history_list
from singulr.services.telegram_actions import format_pending_review_body


def test_format_ban_history_list_includes_date_and_reason() -> None:
    """Admin ban history lines include date, reason, and category."""
    ban = Ban(
        telegram_user_id=1,
        fingerprint_hash="0x" + "a" * 64,
        reason="spam raid",
        category="spam",
        banned_at=datetime(2026, 1, 15, tzinfo=UTC),
    )
    text = format_ban_history_list([ban])
    assert "2026-01-15" in text
    assert "spam raid" in text
    assert "spam" in text


def test_pending_review_body_includes_ban_history() -> None:
    """Pending ops card embeds formatted ban history."""
    body = format_pending_review_body(
        user_id=42,
        reason="Network review",
        ban_history="• Banned on 2026-01-01 for test (scam_fraud)",
    )
    assert "Prior bans" in body
    assert "scam_fraud" in body
