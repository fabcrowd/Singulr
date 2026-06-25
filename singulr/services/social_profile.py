"""Social profile scoring via pluggable external providers."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from singulr.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SocialProfileResult:
    """Outcome of social profile analysis."""

    risk_score: int = 0
    hard_categories: list[str] = field(default_factory=list)
    soft_signals: list[str] = field(default_factory=list)
    summary: str = ""


class SocialProfileProvider(Protocol):
    """Analyze a Telegram member for bot/impersonation and soft risk signals."""

    async def analyze(
        self,
        *,
        telegram_user_id: int,
        username: str | None = None,
        display_name: str | None = None,
    ) -> SocialProfileResult:
        """Return social profile scoring for verify decisions."""


class MockSocialProfileProvider:
    """Test provider driven by env MOCK_SOCIAL_HARD_USER_IDS."""

    async def analyze(
        self,
        *,
        telegram_user_id: int,
        username: str | None = None,
        display_name: str | None = None,
    ) -> SocialProfileResult:
        settings = get_settings()
        hard_ids = {int(x) for x in settings.mock_social_hard_user_ids.split(",") if x.strip()}
        soft_ids = {int(x) for x in settings.mock_social_soft_user_ids.split(",") if x.strip()}
        if telegram_user_id in hard_ids:
            return SocialProfileResult(
                risk_score=95,
                hard_categories=["bot_abuse"],
                summary="Mock: high-confidence bot signals",
            )
        if telegram_user_id in soft_ids:
            return SocialProfileResult(
                risk_score=55,
                soft_signals=["suspicious_username"],
                summary="Mock: elevated social risk",
            )
        return SocialProfileResult()


class NoOpSocialProfileProvider:
    """Disabled provider."""

    async def analyze(
        self,
        *,
        telegram_user_id: int,
        username: str | None = None,
        display_name: str | None = None,
    ) -> SocialProfileResult:
        return SocialProfileResult()


def get_social_profile_provider() -> SocialProfileProvider:
    """Factory from SOCIAL_PROFILE_PROVIDER env."""
    settings = get_settings()
    if settings.social_profile_provider == "mock":
        return MockSocialProfileProvider()
    return NoOpSocialProfileProvider()
