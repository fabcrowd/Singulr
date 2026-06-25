"""Tests for network reputation scoring."""

from __future__ import annotations

import pytest

from singulr.domain.ban_taxonomy import BanCategory, BanSeverity
from singulr.services.channel_policy import EffectivePolicy
from singulr.services.network_reputation import (
    compute_network_score,
    network_decision_from_score,
)


def _policy(**overrides: object) -> EffectivePolicy:
    """Build EffectivePolicy with defaults for network tests."""
    base = {
        "channel_id": 1,
        "security_preset": "balanced",
        "ban_evasion_auto_deny_threshold": 0.92,
        "local_similarity_flag_threshold": 0.85,
        "network_registry_mode": "read",
        "share_bans_to_network": False,
        "network_auto_reject_categories": ["scam_fraud", "raid_coordination"],
        "instant_ban_categories": ["impersonation", "bot_abuse"],
        "admin_ops_chat_id": None,
    }
    base.update(overrides)
    return EffectivePolicy(**base)  # type: ignore[arg-type]


def test_scam_fraud_permanent_triggers_auto_reject_score() -> None:
    """Permanent scam_fraud in auto-reject list yields max score."""
    score = compute_network_score(
        [{"category": BanCategory.SCAM_FRAUD.value, "severity": BanSeverity.PERMANENT.value}],
        policy=_policy(),
    )
    assert score >= 10_000


def test_score_between_review_and_reject_yields_pending() -> None:
    """Mid-band network score maps to pending review."""
    outcome = network_decision_from_score(55, policy=_policy())
    assert outcome == "pending"


def test_score_above_reject_yields_block() -> None:
    """High network score maps to block."""
    outcome = network_decision_from_score(120, policy=_policy())
    assert outcome == "block"


def test_network_registry_off_skips_decision() -> None:
    """Off mode returns None so local checks continue."""
    outcome = network_decision_from_score(200, policy=_policy(network_registry_mode="off"))
    assert outcome is None


@pytest.mark.asyncio
async def test_matching_blocks_on_high_network_score(
    db_session,
) -> None:
    """check_known_bad sends high network score to pending review."""
    from unittest.mock import AsyncMock, MagicMock

    from singulr.models import Ban
    from singulr.services.matching import Decision, check_known_bad

    fingerprint = "0x" + "bb" * 32
    verify_fp = "0x" + "cc" * 32
    db_session.add(
        Ban(
            telegram_user_id=999,
            fingerprint_hash=fingerprint,
            reason="scam",
            category=BanCategory.HARASSMENT.value,
            severity=BanSeverity.HIGH.value,
        )
    )
    await db_session.commit()

    chain = MagicMock()
    chain.is_banned = AsyncMock(return_value=False)
    chain.get_reputation = AsyncMock(return_value={"score": 120, "active_bans": 1})

    result = await check_known_bad(
        db_session,
        chain,
        telegram_user_id=1000,
        fingerprint_hash=verify_fp,
        ip_hash=None,
        channel_id=42,
    )

    assert result.decision == Decision.PENDING
    assert any("network_score" in factor for factor in result.risk_factors)
