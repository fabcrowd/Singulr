"""Tests for Python-to-chain ban taxonomy ordinals."""

from __future__ import annotations

import pytest

from singulr.domain.ban_taxonomy import BanCategory, BanSeverity
from singulr.domain.chain_mapping import category_to_chain, severity_to_chain

# Ordinals must stay aligned with contracts/BanRegistry.sol enum declaration order.
_CATEGORY_ORDINALS: list[tuple[BanCategory, int]] = [
    (BanCategory.SPAM, 0),
    (BanCategory.SOLICITATION, 1),
    (BanCategory.SCAM_FRAUD, 2),
    (BanCategory.HARASSMENT, 3),
    (BanCategory.BOT_ABUSE, 4),
    (BanCategory.IMPERSONATION, 5),
    (BanCategory.NSFW, 6),
    (BanCategory.RAID_COORDINATION, 7),
    (BanCategory.OTHER, 8),
]

_SEVERITY_ORDINALS: list[tuple[BanSeverity, int]] = [
    (BanSeverity.LOW, 0),
    (BanSeverity.MEDIUM, 1),
    (BanSeverity.HIGH, 2),
    (BanSeverity.PERMANENT, 3),
]


@pytest.mark.parametrize(("category", "ordinal"), _CATEGORY_ORDINALS)
def test_category_to_chain_matches_ban_registry(category: BanCategory, ordinal: int) -> None:
    """Each BanCategory maps to the BanRegistry.sol enum ordinal."""
    assert category_to_chain(category) == ordinal
    assert category_to_chain(category.value) == ordinal


@pytest.mark.parametrize(("severity", "ordinal"), _SEVERITY_ORDINALS)
def test_severity_to_chain_matches_ban_registry(severity: BanSeverity, ordinal: int) -> None:
    """Each BanSeverity maps to the BanRegistry.sol enum ordinal."""
    assert severity_to_chain(severity) == ordinal
    assert severity_to_chain(severity.value) == ordinal
