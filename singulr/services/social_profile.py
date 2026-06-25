"""Social profile scoring via Telegram-native heuristics and pluggable providers."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.config import get_settings
from singulr.models import VerificationToken
from singulr.services.channel_policy import EffectivePolicy

logger = logging.getLogger(__name__)

SUSPICIOUS_USERNAME_PARTS = ("support", "official", "admin", "helpdesk", "verify", "mod")
DEFAULT_PENDING_SCORE_THRESHOLD = 40


class SocialProfileProviderError(Exception):
    """Raised when all configured social providers fail."""


@dataclass(frozen=True)
class SocialProfileContext:
    """Inputs for a single social profile analysis pass."""

    telegram_user_id: int
    channel_id: int
    username: str | None = None
    display_name: str | None = None
    language_code: str | None = None
    channel_title: str | None = None
    verify_token: str | None = None


@dataclass(frozen=True)
class SocialProfileResult:
    """Outcome of social profile analysis."""

    risk_score: int = 0
    hard_categories: list[str] = field(default_factory=list)
    soft_signals: list[str] = field(default_factory=list)
    summary: str = ""
    sources: list[str] = field(default_factory=list)


def result_to_cache_dict(result: SocialProfileResult) -> dict[str, Any]:
    """Serialize a result for token-row cache storage."""
    return {
        "risk_score": result.risk_score,
        "hard_categories": list(result.hard_categories),
        "soft_signals": list(result.soft_signals),
        "summary": result.summary,
        "sources": list(result.sources),
    }


def result_from_cache_dict(data: dict[str, Any]) -> SocialProfileResult:
    """Deserialize a cached social profile result."""
    return SocialProfileResult(
        risk_score=int(data.get("risk_score", 0)),
        hard_categories=list(data.get("hard_categories") or []),
        soft_signals=list(data.get("soft_signals") or []),
        summary=str(data.get("summary") or ""),
        sources=list(data.get("sources") or []),
    )


def merge_social_results(*results: SocialProfileResult) -> SocialProfileResult:
    """Merge provider outputs into one combined result."""
    hard: list[str] = []
    soft: list[str] = []
    sources: list[str] = []
    summaries: list[str] = []
    score = 0
    for result in results:
        score = max(score, result.risk_score)
        for category in result.hard_categories:
            if category not in hard:
                hard.append(category)
        for signal in result.soft_signals:
            if signal not in soft:
                soft.append(signal)
        for source in result.sources:
            if source not in sources:
                sources.append(source)
        if result.summary:
            summaries.append(result.summary)
    return SocialProfileResult(
        risk_score=score,
        hard_categories=hard,
        soft_signals=soft,
        summary="; ".join(summaries),
        sources=sources,
    )


class SocialProfileProvider(Protocol):
    """Analyze a Telegram member for bot/impersonation and soft risk signals."""

    async def analyze(self, ctx: SocialProfileContext) -> SocialProfileResult:
        """Return social profile scoring for verify decisions."""


def _normalize_text(value: str) -> str:
    """Lowercase and trim for heuristic comparisons."""
    return value.lower().strip()


class TelegramNativeProvider:
    """Heuristic scoring from Telegram-visible profile fields only."""

    async def analyze(self, ctx: SocialProfileContext) -> SocialProfileResult:
        """Apply local rules; Tier 1 never emits hard categories."""
        soft_signals: list[str] = []
        score = 0

        if not ctx.username:
            soft_signals.append("no_username")
            score = max(score, 25)

        if ctx.username:
            username = _normalize_text(ctx.username)
            for part in SUSPICIOUS_USERNAME_PARTS:
                if part in username:
                    soft_signals.append(f"username_{part}_pattern")
                    score = max(score, 45)
                    break

        if not ctx.display_name or not ctx.display_name.strip():
            soft_signals.append("empty_display_name")
            score = max(score, 20)

        if ctx.channel_title and ctx.display_name:
            title_words = [
                word
                for word in _normalize_text(ctx.channel_title).split()
                if len(word) >= 4
            ]
            display = _normalize_text(ctx.display_name)
            if title_words and any(word in display for word in title_words):
                soft_signals.append("display_name_brand_overlap")
                score = max(score, 50)

        if not soft_signals:
            return SocialProfileResult(sources=["telegram_native"])

        summary = f"Telegram heuristics: {', '.join(soft_signals)}"
        return SocialProfileResult(
            risk_score=score,
            soft_signals=soft_signals,
            summary=summary,
            sources=["telegram_native"],
        )


class MockSocialProfileProvider:
    """Test provider driven by env MOCK_SOCIAL_HARD_USER_IDS."""

    async def analyze(self, ctx: SocialProfileContext) -> SocialProfileResult:
        settings = get_settings()
        hard_ids = {int(x) for x in settings.mock_social_hard_user_ids.split(",") if x.strip()}
        soft_ids = {int(x) for x in settings.mock_social_soft_user_ids.split(",") if x.strip()}
        if ctx.telegram_user_id in hard_ids:
            return SocialProfileResult(
                risk_score=95,
                hard_categories=["bot_abuse"],
                summary="Mock: high-confidence bot signals",
                sources=["mock"],
            )
        if ctx.telegram_user_id in soft_ids:
            return SocialProfileResult(
                risk_score=55,
                soft_signals=["suspicious_username"],
                summary="Mock: elevated social risk",
                sources=["mock"],
            )
        return SocialProfileResult()


class CompositeSocialProfileProvider:
    """Run multiple providers and merge their results."""

    def __init__(self, providers: list[SocialProfileProvider]) -> None:
        self._providers = providers

    async def analyze(self, ctx: SocialProfileContext) -> SocialProfileResult:
        """Merge all provider results; raise when every provider fails."""
        if not self._providers:
            return SocialProfileResult()
        merged = SocialProfileResult()
        errors = 0
        for provider in self._providers:
            try:
                merged = merge_social_results(merged, await provider.analyze(ctx))
            except SocialProfileProviderError:
                errors += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("social provider %s failed: %s", type(provider).__name__, exc)
                errors += 1
        if errors == len(self._providers):
            raise SocialProfileProviderError("all social providers failed")
        return merged


def get_composite_provider() -> CompositeSocialProfileProvider:
    """Build the active provider stack from settings."""
    providers: list[SocialProfileProvider] = [TelegramNativeProvider()]
    if get_settings().social_profile_provider == "mock":
        providers.append(MockSocialProfileProvider())
    return CompositeSocialProfileProvider(providers)


def get_social_profile_provider() -> CompositeSocialProfileProvider:
    """Factory for backward-compatible call sites."""
    return get_composite_provider()


async def _find_token_for_cache(
    session: AsyncSession,
    ctx: SocialProfileContext,
) -> VerificationToken | None:
    """Resolve the token row used for social profile caching."""
    if ctx.verify_token:
        return await session.scalar(
            select(VerificationToken).where(VerificationToken.token == ctx.verify_token)
        )
    return await session.scalar(
        select(VerificationToken)
        .where(
            VerificationToken.telegram_user_id == ctx.telegram_user_id,
            VerificationToken.channel_id == ctx.channel_id,
        )
        .order_by(VerificationToken.created_at.desc())
        .limit(1)
    )


async def get_cached_social_profile(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    channel_id: int,
    verify_token: str | None = None,
) -> SocialProfileResult | None:
    """Return cached social analysis for a verify session if present."""
    ctx = SocialProfileContext(
        telegram_user_id=telegram_user_id,
        channel_id=channel_id,
        verify_token=verify_token,
    )
    token_row = await _find_token_for_cache(session, ctx)
    if token_row and token_row.social_profile_cache:
        return result_from_cache_dict(token_row.social_profile_cache)
    return None


async def analyze_social_profile(
    session: AsyncSession,
    ctx: SocialProfileContext,
    *,
    policy: EffectivePolicy,
    token_row: VerificationToken | None = None,
    refresh: bool = False,
) -> SocialProfileResult:
    """Run social analysis with token-row cache and fail-mode policy."""
    if not policy.social_profiling_enabled:
        return SocialProfileResult()

    if token_row is None:
        token_row = await _find_token_for_cache(session, ctx)

    if not refresh and token_row and token_row.social_profile_cache:
        logger.info(
            "social_profile_analyze cache_hit=1 duration_ms=0 user_id=%s channel_id=%s",
            ctx.telegram_user_id,
            ctx.channel_id,
        )
        return result_from_cache_dict(token_row.social_profile_cache)

    started = time.perf_counter()
    try:
        result = await get_composite_provider().analyze(ctx)
    except SocialProfileProviderError:
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.warning(
            "social_profile_analyze provider_error=1 duration_ms=%s user_id=%s",
            duration_ms,
            ctx.telegram_user_id,
        )
        if policy.social_api_fail_mode == "fail_closed":
            raise
        return SocialProfileResult(summary="Social check unavailable")

    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "social_profile_analyze cache_hit=0 duration_ms=%s sources=%s user_id=%s",
        duration_ms,
        ",".join(result.sources) or "none",
        ctx.telegram_user_id,
    )

    if token_row is not None:
        token_row.social_profile_cache = result_to_cache_dict(result)
        token_row.social_analyzed_at = datetime.now(UTC)
        await session.flush()

    return result
