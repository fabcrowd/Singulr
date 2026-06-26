"""Self-hosted Telegram user blocklist for social profile scoring."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from singulr.services.social_profile import (
    SocialProfileContext,
    SocialProfileProviderError,
    SocialProfileResult,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BlocklistEntry:
    """One blocklisted Telegram user."""

    telegram_user_id: int
    category: str
    reason: str = ""


def load_blocklist(path: str | Path) -> dict[int, BlocklistEntry]:
    """Load blocklist JSON into a user-id index."""
    file_path = Path(path)
    if not file_path.is_file():
        raise SocialProfileProviderError(f"blocklist file not found: {file_path}")
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    entries: dict[int, BlocklistEntry] = {}
    for item in raw.get("entries", []):
        user_id = int(item["telegram_user_id"])
        entries[user_id] = BlocklistEntry(
            telegram_user_id=user_id,
            category=str(item.get("category", "other")),
            reason=str(item.get("reason", "")),
        )
    return entries


class BlocklistProvider:
    """Match joiners against a local JSON blocklist file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._entries: dict[int, BlocklistEntry] | None = None

    def _ensure_loaded(self) -> dict[int, BlocklistEntry]:
        if self._entries is None:
            self._entries = load_blocklist(self._path)
        return self._entries

    async def analyze(self, ctx: SocialProfileContext) -> SocialProfileResult:
        """Return hard category when user id is on the blocklist."""
        entry = self._ensure_loaded().get(ctx.telegram_user_id)
        if entry is None:
            return SocialProfileResult(sources=["blocklist"])
        summary = entry.reason or f"Blocklist hit ({entry.category})"
        logger.info(
            "blocklist hit user_id=%s category=%s",
            ctx.telegram_user_id,
            entry.category,
        )
        return SocialProfileResult(
            risk_score=90,
            hard_categories=[entry.category],
            summary=summary,
            sources=["blocklist"],
        )
