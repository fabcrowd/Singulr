"""Map Python ban taxonomy enums to on-chain BanRegistry ordinals."""

from __future__ import annotations

from singulr.domain.ban_taxonomy import BanCategory, BanSeverity

# Ordinals must match contracts/BanRegistry.sol enum order.
CATEGORY_TO_CHAIN: dict[BanCategory, int] = {
    BanCategory.SPAM: 0,
    BanCategory.SOLICITATION: 1,
    BanCategory.SCAM_FRAUD: 2,
    BanCategory.HARASSMENT: 3,
    BanCategory.BOT_ABUSE: 4,
    BanCategory.IMPERSONATION: 5,
    BanCategory.NSFW: 6,
    BanCategory.RAID_COORDINATION: 7,
    BanCategory.OTHER: 8,
}

SEVERITY_TO_CHAIN: dict[BanSeverity, int] = {
    BanSeverity.LOW: 0,
    BanSeverity.MEDIUM: 1,
    BanSeverity.HIGH: 2,
    BanSeverity.PERMANENT: 3,
}


def category_to_chain(category: BanCategory | str) -> int:
    """Return uint8 category ordinal for the chain contract."""
    if isinstance(category, str):
        category = BanCategory(category)
    return CATEGORY_TO_CHAIN[category]


def severity_to_chain(severity: BanSeverity | str) -> int:
    """Return uint8 severity ordinal for the chain contract."""
    if isinstance(severity, str):
        severity = BanSeverity(severity)
    return SEVERITY_TO_CHAIN[severity]
