"""Verification decision engine and known-bad registry checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.config import get_settings
from singulr.models import Ban, IPSession, Profile
from singulr.services.blockchain import ChainClient
from singulr.services.channel_policy import EffectivePolicy, get_effective_channel_policy
from singulr.services.keystroke import keystroke_similarity
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
        admin_ops_chat_id=settings.log_channel_id or None,
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
) -> MatchResult:
    """Run tiered checks: exact bans, chain, IP flag, env anomaly, keystroke/stylometry."""
    effective_policy = await _resolve_effective_policy(
        session, channel_id=channel_id, policy=policy
    )
    factors: list[str] = []

    ban_by_user = await session.scalar(
        select(Ban).where(Ban.telegram_user_id == telegram_user_id)
    )
    if ban_by_user:
        return MatchResult(
            Decision.BLOCK,
            "Known banned user ID",
            ["exact_user_id_match"],
            matched_ban_id=ban_by_user.id,
        )

    ban_by_fp = await session.scalar(select(Ban).where(Ban.fingerprint_hash == fingerprint_hash))
    if ban_by_fp:
        return MatchResult(
            Decision.BLOCK,
            "Known banned device fingerprint",
            ["exact_fingerprint_match"],
            matched_ban_id=ban_by_fp.id,
        )

    if await chain.is_banned(fingerprint_hash):
        return MatchResult(
            Decision.BLOCK,
            "On-chain shared blacklist",
            ["chain_blacklist"],
        )

    if ip_hash:
        ip_ban = await session.scalar(select(Ban).where(Ban.ip_hash == ip_hash))
        if ip_ban:
            factors.append("ip_hash_match")
        if await check_ip_velocity(session, ip_hash):
            factors.append("ip_velocity")

    if _env_anomaly_detected(env_flags):
        factors.append(f"env_anomaly:+{ENV_ANOMALY_RISK}")

    bans = (await session.scalars(select(Ban))).all()
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

    if factors:
        return MatchResult(Decision.FLAG, "Elevated risk — review recommended", factors)

    return MatchResult(Decision.APPROVE, "Clean", [])
