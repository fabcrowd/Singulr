"""Verification decision engine and known-bad registry checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.config import get_settings
from singulr.models import Ban, IPSession, Profile, VerificationToken
from singulr.services.automation_score import compute_automation_score, resolve_automation_outcome
from singulr.services.blockchain import ChainClient
from singulr.services.channel_policy import (
    DEFAULT_INSTANT_BAN_CATEGORIES,
    DEFAULT_NETWORK_AUTO_REJECT,
    EffectivePolicy,
    get_effective_channel_policy,
)
from singulr.services.keystroke import keystroke_similarity
from singulr.services.keystroke_validation import keystroke_risk_factors_from_profile
from singulr.services.network_reputation import (
    compute_network_score,
    network_decision_from_score,
)
from singulr.services.reinstatement import is_ban_blocking
from singulr.services.social_profile import (
    SocialProfileContext,
    SocialProfileProviderError,
    analyze_social_profile,
)
from singulr.services.stylometry import stylometry_similarity

ENV_ANOMALY_RISK = 20


class Decision(str, Enum):
    """Verification outcome."""

    APPROVE = "approve"
    FLAG = "flag"
    PENDING = "pending"
    BLOCK = "block"


@dataclass
class MatchResult:
    """Result of registry and similarity checks."""

    decision: Decision
    reason: str
    risk_factors: list[str] = field(default_factory=list)
    matched_ban_id: int | None = None
    keystroke_score: float | None = None
    stylometry_score: float | None = None


def _env_anomaly_detected(env_flags: dict | None) -> bool:
    """True when browser reports automation or headless signals."""
    if not env_flags:
        return False
    return bool(env_flags.get("webdriver") or env_flags.get("headless_ua"))


def _is_ban_evasion_match(ban: Ban | None, telegram_user_id: int) -> bool:
    """True when similarity links a new user to a banned identity."""
    if ban is None:
        return False
    if ban.telegram_user_id is None:
        return True
    return ban.telegram_user_id != telegram_user_id


async def _resolve_effective_policy(
    session: AsyncSession,
    *,
    channel_id: int | None,
    policy: EffectivePolicy | None,
) -> EffectivePolicy:
    """Load channel policy or build defaults from settings."""
    if policy is not None:
        return policy
    if channel_id is not None:
        return await get_effective_channel_policy(session, channel_id)
    settings = get_settings()
    return EffectivePolicy(
        channel_id=channel_id or 0,
        security_preset=settings.default_security_preset,
        ban_evasion_auto_deny_threshold=settings.ban_evasion_auto_deny_threshold,
        local_similarity_flag_threshold=settings.local_similarity_flag_threshold,
        network_registry_mode=settings.default_network_registry_mode,
        share_bans_to_network=False,
        network_auto_reject_categories=list(DEFAULT_NETWORK_AUTO_REJECT),
        instant_ban_categories=list(DEFAULT_INSTANT_BAN_CATEGORIES),
        social_profiling_enabled=settings.default_social_profiling_enabled,
        social_api_fail_mode=settings.default_social_api_fail_mode,
        social_pending_score_threshold=settings.default_social_pending_score_threshold,
        social_external_api_enabled=False,
        admin_ops_chat_id=settings.log_channel_id or None,
        automation_flag_mode=settings.default_automation_flag_mode,
        ai_pending_score_threshold=settings.default_ai_pending_score_threshold,
    )


def _ban_evasion_result(
    *,
    score: float,
    score_label: str,
    matched_ban: Ban | None,
    policy: EffectivePolicy,
    factors: list[str],
    keystroke_score: float | None = None,
    stylometry_score: float | None = None,
) -> MatchResult | None:
    """Map similarity score to BLOCK or PENDING for ban-evasion cases."""
    if score >= policy.ban_evasion_auto_deny_threshold:
        factors.append(f"{score_label}:{score:.2f}")
        return MatchResult(
            Decision.BLOCK,
            f"Ban evasion — high {score_label.replace('_', ' ')}",
            factors,
            matched_ban_id=matched_ban.id if matched_ban else None,
            keystroke_score=keystroke_score,
            stylometry_score=stylometry_score,
        )
    if score >= policy.local_similarity_flag_threshold:
        factors.append(f"{score_label}:{score:.2f}")
        return MatchResult(
            Decision.PENDING,
            f"Possible ban evasion — {score_label.replace('_', ' ')}",
            factors,
            matched_ban_id=matched_ban.id if matched_ban else None,
            keystroke_score=keystroke_score,
            stylometry_score=stylometry_score,
        )
    return None


async def check_ip_velocity(session: AsyncSession, ip_hash: str) -> bool:
    """True when the same IP hash verified 2+ distinct users within 24 hours."""
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    distinct_users = await session.scalar(
        select(func.count(func.distinct(IPSession.telegram_user_id))).where(
            IPSession.ip_hash == ip_hash,
            IPSession.timestamp >= cutoff,
        )
    )
    return (distinct_users or 0) >= 2


async def check_known_bad(
    session: AsyncSession,
    chain: ChainClient,
    *,
    telegram_user_id: int,
    fingerprint_hash: str,
    ip_hash: str | None,
    keystroke_profile: dict | None = None,
    stylometry_vector: dict | None = None,
    env_flags: dict | None = None,
    channel_id: int | None = None,
    policy: EffectivePolicy | None = None,
    token_row: VerificationToken | None = None,
    social_context: SocialProfileContext | None = None,
) -> MatchResult:
    """Run tiered checks: exact bans, chain, IP flag, env anomaly, keystroke/stylometry."""
    effective_policy = await _resolve_effective_policy(
        session, channel_id=channel_id, policy=policy
    )
    factors: list[str] = []

    ban_by_user = await session.scalar(
        select(Ban).where(
            Ban.telegram_user_id == telegram_user_id,
            Ban.status == "active",
        )
    )
    if ban_by_user:
        return MatchResult(
            Decision.BLOCK,
            "Known banned user ID",
            ["exact_user_id_match"],
            matched_ban_id=ban_by_user.id,
        )

    ban_by_fp = await session.scalar(
        select(Ban).where(
            Ban.fingerprint_hash == fingerprint_hash,
            Ban.status == "active",
        )
    )
    if ban_by_fp:
        return MatchResult(
            Decision.BLOCK,
            "Known banned device fingerprint",
            ["exact_fingerprint_match"],
            matched_ban_id=ban_by_fp.id,
        )

    if await chain.is_banned(fingerprint_hash):
        factors.append("chain_blacklist")
        return MatchResult(
            Decision.PENDING,
            "Cross-channel network history requires review",
            factors,
        )

    if effective_policy.network_registry_mode != "off":
        reputation = await chain.get_reputation(fingerprint_hash)
        if reputation["active_bans"] > 0:
            related_bans = (
                await session.scalars(select(Ban).where(Ban.fingerprint_hash == fingerprint_hash))
            ).all()
            active_meta = [
                {"category": ban.category, "severity": ban.severity}
                for ban in related_bans
                if is_ban_blocking(ban)
            ]
            network_score = reputation["score"]
            if active_meta:
                network_score = max(
                    network_score, compute_network_score(active_meta, policy=effective_policy)
                )
            factors.append(f"network_score:{network_score}")
            network_outcome = network_decision_from_score(
                network_score, policy=effective_policy
            )
            if network_outcome == "block":
                return MatchResult(
                    Decision.PENDING,
                    "Network reputation review",
                    factors,
                )
            if network_outcome == "pending":
                return MatchResult(
                    Decision.PENDING,
                    "Network reputation review",
                    factors,
                )

    if ip_hash:
        ip_ban = await session.scalar(
            select(Ban).where(Ban.ip_hash == ip_hash, Ban.status == "active")
        )
        if ip_ban:
            factors.append("ip_hash_match")
        if await check_ip_velocity(session, ip_hash):
            factors.append("ip_velocity")

    if _env_anomaly_detected(env_flags):
        factors.append(f"env_anomaly:+{ENV_ANOMALY_RISK}")

    if keystroke_profile:
        factors.extend(keystroke_risk_factors_from_profile(keystroke_profile))

    automation_score = compute_automation_score(env_flags, factors)
    if automation_score > 0:
        factors.append(f"automation_score:{automation_score}")
    automation_outcome = resolve_automation_outcome(
        automation_score,
        policy=effective_policy,
    )
    if automation_outcome is not None:
        if automation_outcome.action == "block":
            return MatchResult(Decision.BLOCK, automation_outcome.reason, factors)
        return MatchResult(Decision.PENDING, automation_outcome.reason, factors)

    bans = (
        await session.scalars(select(Ban).where(Ban.status == "active"))
    ).all()
    best_keystroke = 0.0
    best_stylo = 0.0
    keystroke_matched_ban: Ban | None = None
    stylo_matched_ban: Ban | None = None

    if keystroke_profile:
        for ban in bans:
            profiles = (
                await session.scalars(
                    select(Profile).where(Profile.fingerprint_hash == ban.fingerprint_hash)
                )
            ).all()
            for profile in profiles:
                score = keystroke_similarity(keystroke_profile, profile.keystroke_profile)
                if score > best_keystroke:
                    best_keystroke = score
                    keystroke_matched_ban = ban

    if stylometry_vector and bans:
        from singulr.models import StylometryProfile

        for ban in bans:
            if not ban.stylometry_hash or not ban.telegram_user_id:
                continue
            row = await session.get(StylometryProfile, ban.telegram_user_id)
            if not row or not row.feature_vector:
                continue
            score = stylometry_similarity(stylometry_vector, row.feature_vector)
            if score > best_stylo:
                best_stylo = score
                stylo_matched_ban = ban

    if keystroke_profile and _is_ban_evasion_match(keystroke_matched_ban, telegram_user_id):
        evasion = _ban_evasion_result(
            score=best_keystroke,
            score_label="keystroke_similarity",
            matched_ban=keystroke_matched_ban,
            policy=effective_policy,
            factors=factors.copy(),
            keystroke_score=best_keystroke,
        )
        if evasion is not None:
            return evasion

    if stylometry_vector and _is_ban_evasion_match(stylo_matched_ban, telegram_user_id):
        evasion = _ban_evasion_result(
            score=best_stylo,
            score_label="stylometry_similarity",
            matched_ban=stylo_matched_ban,
            policy=effective_policy,
            factors=factors.copy(),
            stylometry_score=best_stylo,
        )
        if evasion is not None:
            return evasion

    if token_row:
        ctx = SocialProfileContext(
            telegram_user_id=telegram_user_id,
            channel_id=channel_id or effective_policy.channel_id,
            username=token_row.join_username,
            display_name=token_row.join_display_name,
            language_code=token_row.join_language_code,
            channel_title=token_row.join_channel_title,
            verify_token=token_row.token,
        )
    else:
        ctx = social_context or SocialProfileContext(
            telegram_user_id=telegram_user_id,
            channel_id=channel_id or effective_policy.channel_id,
        )
    try:
        social = await analyze_social_profile(
            session,
            ctx,
            policy=effective_policy,
            token_row=token_row,
        )
    except SocialProfileProviderError:
        return MatchResult(
            Decision.PENDING,
            "Social profile check unavailable",
            factors + ["social_provider_error"],
        )
    if social.hard_categories:
        for category in social.hard_categories:
            if category in effective_policy.instant_ban_categories:
                factors.append(f"social_hard:{category}")
                return MatchResult(
                    Decision.BLOCK,
                    f"Social profile — {category}",
                    factors,
                )
    if social.risk_score >= effective_policy.social_pending_score_threshold:
        for signal in social.soft_signals:
            factors.append(f"social_soft:{signal}")
        factors.append(f"social_score:{social.risk_score}")
        return MatchResult(
            Decision.PENDING,
            "Social profile review",
            factors,
        )

    if factors:
        return MatchResult(Decision.FLAG, "Elevated risk — review recommended", factors)

    return MatchResult(Decision.APPROVE, "Clean", [])
