"""Tests for self-hosted social blocklist provider."""

from __future__ import annotations

from pathlib import Path

import pytest

from singulr.services.social_blocklist import BlocklistProvider, load_blocklist
from singulr.services.social_profile import SocialProfileContext

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "social_blocklist.json"


def test_load_blocklist_indexes_entries() -> None:
    """Blocklist JSON loads into a user-id map."""
    entries = load_blocklist(_FIXTURE)
    assert 990001 in entries
    assert entries[990001].category == "scam_fraud"


@pytest.mark.asyncio
async def test_blocklist_provider_hard_category_for_known_user() -> None:
    """Known blocklist user returns hard scam_fraud category."""
    provider = BlocklistProvider(_FIXTURE)
    result = await provider.analyze(
        SocialProfileContext(telegram_user_id=990001, channel_id=42)
    )
    assert "scam_fraud" in result.hard_categories
    assert result.risk_score >= 80
    assert "blocklist" in result.sources


@pytest.mark.asyncio
async def test_blocklist_provider_clean_for_unknown_user() -> None:
    """Unknown users pass through blocklist unchanged."""
    provider = BlocklistProvider(_FIXTURE)
    result = await provider.analyze(
        SocialProfileContext(telegram_user_id=123456, channel_id=42)
    )
    assert not result.hard_categories
    assert "blocklist" in result.sources
