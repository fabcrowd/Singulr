"""Ban recording to database and chain."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.domain.ban_taxonomy import BanCategory, BanSeverity
from singulr.models import Ban, Profile, StylometryProfile
from singulr.services.blockchain import ChainClient
from singulr.services.hashing import hash_fingerprint
from singulr.services.stylometry import stylometry_hash

_chain = ChainClient()


async def record_ban(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    channel_id: int,
    reason: str = "admin_ban",
    category: BanCategory = BanCategory.OTHER,
    severity: BanSeverity = BanSeverity.MEDIUM,
) -> str:
    """Persist ban locally and on-chain; returns fingerprint hash."""
    profile = await session.scalar(
        select(Profile).where(Profile.telegram_user_id == telegram_user_id)
    )
    fingerprint_hash = profile.fingerprint_hash if profile else hash_fingerprint(str(telegram_user_id))

    stylo = await session.get(StylometryProfile, telegram_user_id)
    stylo_hash = stylometry_hash(stylo.feature_vector) if stylo and stylo.feature_vector else None

    existing = await session.scalar(select(Ban).where(Ban.fingerprint_hash == fingerprint_hash))
    if not existing:
        ban = Ban(
            telegram_user_id=telegram_user_id,
            fingerprint_hash=fingerprint_hash,
            stylometry_hash=stylo_hash,
            ip_hash=profile.ip_hash if profile else None,
            reason=reason,
            category=category.value,
            severity=severity.value,
        )
        session.add(ban)
        await session.commit()
        tx = await _chain.record_ban(fingerprint_hash, stylo_hash, channel_id)
        if tx:
            ban.chain_tx = tx
            await session.commit()

    if profile:
        profile.status = "banned"
        await session.commit()

    return fingerprint_hash
