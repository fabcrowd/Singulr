"""Format ban history for admin-only review messages."""

from __future__ import annotations

from datetime import datetime

from singulr.models import Ban


def format_ban_history_list(bans: list[Ban]) -> str:
    """Return admin lines: Banned on {date} for {reason} ({category})."""
    if not bans:
        return "No prior ban records on file."
    lines: list[str] = []
    for ban in bans:
        banned_at: datetime | None = ban.banned_at
        date_label = banned_at.date().isoformat() if banned_at else "unknown date"
        reason = ban.reason.strip() or ban.category
        status_note = f" [{ban.status}]" if ban.status != "active" else ""
        lines.append(f"• Banned on {date_label} for {reason} ({ban.category}){status_note}")
    return "\n".join(lines)
