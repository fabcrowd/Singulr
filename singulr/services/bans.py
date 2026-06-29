"""Ban recording to database and chain."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.config import get_settings
from singulr.domain.ban_taxonomy import BanCategory, BanSeverity
from singulr.models import Ban, Profile, StylometryProfile
from singulr.services.reinstatement import BAN_STATUS_ACTIVE
from singulr.services.blockchain import ChainClient
from singulr.services.channel_policy import EffectivePolicy, get_effective_channel_policy
from singulr.services.hashing import hash_fingerprint
from singulr.services.stylometry import stylometry_hash

_chain = ChainClient()


def should_contribute_to_network(channel_id: int, policy: EffectivePolicy) -> bool:
    """True when a local ban should be written to the shared network registry."""
    settings = get_settings()
    if policy.network_registry_mode != "read_write":
        return False
    if not policy.share_bans_to_network:
        return False
    trusted = settings.trusted_channel_id_list
    if trusted and channel_id not in trusted:
        return False
    return True


async def _upsert_ban_for_fingerprint(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    fingerprint_hash: str,
    stylo_hash: str | None,
    ip_hash: str | None,
    reason: str,
    category: BanCategory,
    severity: BanSeverity,
    channel_id: int,
) -> Ban:
    """Create or reactivate a single ban record for one fingerprint hash."""
    existing = await session.scalar(select(Ban).where(Ban.fingerprint_hash == fingerprint_hash))
    if existing:
        if existing.status != BAN_STATUS_ACTIVE:
            existing.status = BAN_STATUS_ACTIVE
            existing.overturned_at = None
            existing.telegram_user_id = telegram_user_id
            existing.reason = reason
            existing.category = category.value
            existing.severity = severity.value
            existing.stylometry_hash = stylo_hash
            existing.ip_hash = ip_hash
            await session.commit()
        return existing

    ban = Ban(
        telegram_user_id=telegram_user_id,
        fingerprint_hash=fingerprint_hash,
        stylometry_hash=stylo_hash,
        ip_hash=ip_hash,
        reason=reason,
        category=category.value,
        severity=severity.value,
    )
    session.add(ban)
    await session.commit()

    policy = await get_effective_channel_policy(session, channel_id)
    if should_contribute_to_network(channel_id, policy):
        tx = await _chain.record_ban(
            fingerprint_hash,
            stylo_hash,
            channel_id,
            category=category,
            severity=severity,
        )
        if tx:
            ban.chain_tx = tx
            await session.commit()

    return ban


async def record_ban(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    channel_id: int,
    reason: str = "admin_ban",
    category: BanCategory = BanCategory.OTHER,
    severity: BanSeverity = BanSeverity.MEDIUM,
) -> str:
    """Persist bans for ALL known device fingerprints; returns primary fingerprint hash.

    Cross-device coverage: if the user verified on both mobile and desktop, a ban
    record is created for each fingerprint so rejoining on either device is blocked.
    """
    profiles = (
        await session.scalars(select(Profile).where(Profile.telegram_user_id == telegram_user_id))
    ).all()

    stylo = await session.get(StylometryProfile, telegram_user_id)
    stylo_hash = stylometry_hash(stylo.feature_vector) if stylo and stylo.feature_vector else None

    if not profiles:
        fingerprint_hash = hash_fingerprint(str(telegram_user_id))
        await _upsert_ban_for_fingerprint(
            session,
            telegram_user_id=telegram_user_id,
            fingerprint_hash=fingerprint_hash,
            stylo_hash=stylo_hash,
            ip_hash=None,
            reason=reason,
            category=category,
            severity=severity,
            channel_id=channel_id,
        )
        return fingerprint_hash

    primary_hash = profiles[0].fingerprint_hash
    for profile in profiles:
        await _upsert_ban_for_fingerprint(
            session,
            telegram_user_id=telegram_user_id,
            fingerprint_hash=profile.fingerprint_hash,
            stylo_hash=stylo_hash,
            ip_hash=profile.ip_hash,
            reason=reason,
            category=category,
            severity=severity,
            channel_id=channel_id,
        )
        profile.status = "banned"

    await session.commit()
    return primary_hash
