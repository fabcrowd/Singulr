"""Map verification block results to structured ban taxonomy."""

from __future__ import annotations

from singulr.domain.ban_taxonomy import BanCategory, BanSeverity
from singulr.services.matching import MatchResult


def block_ban_taxonomy(result: MatchResult) -> tuple[BanCategory, BanSeverity, str]:
    """Choose category and severity for an auto-ban from a match result."""
    reason_lower = result.reason.lower()
    factors = " ".join(result.risk_factors).lower()

    if "impersonation" in reason_lower or "impersonation" in factors:
        return BanCategory.IMPERSONATION, BanSeverity.HIGH, result.reason
    if "bot" in reason_lower or "bot_abuse" in factors:
        return BanCategory.BOT_ABUSE, BanSeverity.HIGH, result.reason
    if "evasion" in reason_lower or result.matched_ban_id is not None:
        return BanCategory.OTHER, BanSeverity.HIGH, result.reason
    if "scam" in reason_lower or "fraud" in reason_lower:
        return BanCategory.SCAM_FRAUD, BanSeverity.PERMANENT, result.reason

    return BanCategory.OTHER, BanSeverity.MEDIUM, result.reason
