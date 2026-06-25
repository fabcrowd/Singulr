"""Network reputation scoring from on-chain ban records."""

from __future__ import annotations

from singulr.domain.ban_taxonomy import BanCategory
from singulr.services.channel_policy import EffectivePolicy

DEFAULT_REVIEW_MIN = 40
DEFAULT_REJECT_MIN = 80

_CATEGORY_WEIGHT: dict[str, int] = {
    BanCategory.SCAM_FRAUD.value: 50,
    BanCategory.RAID_COORDINATION.value: 50,
    BanCategory.HARASSMENT.value: 30,
    BanCategory.IMPERSONATION.value: 30,
}


def category_weight(category: str) -> int:
    """Weight for a ban category when computing network score."""
    return _CATEGORY_WEIGHT.get(category, 10)


def compute_network_score(
    active_bans: list[dict[str, str | int]],
    *,
    policy: EffectivePolicy,
) -> int:
    """Aggregate weighted score from active ban metadata."""
    total = 0
    auto_reject = set(policy.network_auto_reject_categories or [])
    for ban in active_bans:
        category = str(ban.get("category", BanCategory.OTHER.value))
        severity = str(ban.get("severity", "medium"))
        if category in auto_reject and severity == "permanent":
            return 10_000
        weight = category_weight(category)
        if severity == "permanent":
            weight += 100
        elif severity == "high":
            weight += 50
        elif severity == "medium":
            weight += 25
        else:
            weight += 10
        total += weight
    return total


def network_decision_from_score(
    score: int,
    *,
    policy: EffectivePolicy,
    review_min: int = DEFAULT_REVIEW_MIN,
    reject_min: int = DEFAULT_REJECT_MIN,
) -> str | None:
    """Map network score to block, pending, or None (continue local checks)."""
    if policy.network_registry_mode == "off":
        return None
    if score >= reject_min:
        return "block"
    if score >= review_min:
        return "pending"
    return None
