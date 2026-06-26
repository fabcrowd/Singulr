"""Tests for verify submit auto-ban taxonomy mapping."""

from __future__ import annotations

import pytest

from singulr.domain.ban_taxonomy import BanCategory, BanSeverity
from singulr.services.matching import Decision, MatchResult
from singulr.services.verify_ban import block_ban_taxonomy


@pytest.mark.parametrize(
    ("result", "expected_category", "expected_severity"),
    [
        (
            MatchResult(
                Decision.BLOCK,
                "Social profile — impersonation",
                ["social_hard:impersonation"],
            ),
            BanCategory.IMPERSONATION,
            BanSeverity.HIGH,
        ),
        (
            MatchResult(
                Decision.BLOCK,
                "Ban evasion — high keystroke similarity",
                ["keystroke_similarity:0.95"],
                matched_ban_id=7,
            ),
            BanCategory.OTHER,
            BanSeverity.HIGH,
        ),
        (
            MatchResult(
                Decision.BLOCK,
                "Social profile — scam_fraud",
                ["social_hard:scam_fraud"],
            ),
            BanCategory.SCAM_FRAUD,
            BanSeverity.HIGH,
        ),
        (
            MatchResult(
                Decision.BLOCK,
                "Automation signals detected",
                ["automation_score:45"],
            ),
            BanCategory.OTHER,
            BanSeverity.MEDIUM,
        ),
    ],
)
def test_block_ban_taxonomy_maps_categories(
    result: MatchResult,
    expected_category: BanCategory,
    expected_severity: BanSeverity,
) -> None:
    """block_ban_taxonomy maps social, evasion, scam, and default block reasons."""
    category, severity, reason = block_ban_taxonomy(result)

    assert category == expected_category
    assert severity == expected_severity
    assert reason == result.reason
