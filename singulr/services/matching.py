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
from singulr.services.keystroke import keystroke_similarity
from singulr.services.stylometry import stylometry_similarity

ENV_ANOMALY_RISK = 20


class Decision(str, Enum):
    """Verification outcome."""

    APPROVE = "approve"
    FLAG = "flag"
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
) -> MatchResult:
    """Run tiered checks: exact bans, chain, IP flag, env anomaly, keystroke/stylometry."""
    settings = get_settings()
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
    matched_ban: Ban | None = None

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
                    matched_ban = ban

    if stylometry_vector and bans:
        from singulr.models import StylometryProfile

        for ban in bans:
            if not ban.stylometry_hash:
                continue
            stylo_rows = (await session.scalars(select(StylometryProfile))).all()
            for row in stylo_rows:
                if row.telegram_user_id and any(
                    b.telegram_user_id == row.telegram_user_id for b in bans if b.telegram_user_id
                ):
                    score = stylometry_similarity(stylometry_vector, row.feature_vector)
                    if score > best_stylo:
                        best_stylo = score
                        matched_ban = ban

    if best_keystroke >= settings.keystroke_similarity_threshold:
        factors.append(f"keystroke_similarity:{best_keystroke:.2f}")
        return MatchResult(
            Decision.FLAG,
            "Probable keystroke match to banned profile",
            factors,
            matched_ban_id=matched_ban.id if matched_ban else None,
            keystroke_score=best_keystroke,
        )

    if best_stylo >= settings.stylometry_similarity_threshold:
        factors.append(f"stylometry_similarity:{best_stylo:.2f}")
        return MatchResult(
            Decision.FLAG,
            "Probable writing-style match to banned profile",
            factors,
            matched_ban_id=matched_ban.id if matched_ban else None,
            stylometry_score=best_stylo,
        )

    if factors:
        return MatchResult(Decision.FLAG, "Elevated risk — review recommended", factors)

    return MatchResult(Decision.APPROVE, "Clean", [])
