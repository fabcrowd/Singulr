"""Standardized ban category and severity enums for local and network registry."""

from __future__ import annotations

from enum import Enum


class BanCategory(str, Enum):
    """Network-wide ban reason category."""

    SPAM = "spam"
    SOLICITATION = "solicitation"
    SCAM_FRAUD = "scam_fraud"
    HARASSMENT = "harassment"
    BOT_ABUSE = "bot_abuse"
    IMPERSONATION = "impersonation"
    NSFW = "nsfw"
    RAID_COORDINATION = "raid_coordination"
    OTHER = "other"


class BanSeverity(str, Enum):
    """Ban severity tier affecting score weight and decay."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PERMANENT = "permanent"
