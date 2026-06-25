"""Hybrid reinstatement: local unban, time decay, and appeals."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.config import get_settings
from singulr.domain.ban_taxonomy import BanCategory, BanSeverity
from singulr.models import AppealRecord, Ban, Profile
from singulr.services.blockchain import ChainClient

BAN_STATUS_ACTIVE = "active"
BAN_STATUS_OVERTURNED = "overturned"
BAN_STATUS_EXPIRED = "expired"

APPEAL_STATUS_PENDING = "pending"
APPEAL_STATUS_APPROVED = "approved"
APPEAL_STATUS_DENIED = "denied"

PERMANENT_NO_DECAY_CATEGORIES = frozenset(
    {
        BanCategory.SCAM_FRAUD.value,
        BanCategory.RAID_COORDINATION.value,
    }
)

_DECAY_SEVERITIES = frozenset({BanSeverity.LOW.value, BanSeverity.MEDIUM.value})


def reinstatement_success_message() -> str:
    """DM copy after a successful local unban or approved appeal."""
    return (
        "Your reinstatement request was approved. "
        "You may verify again using the link from the channel join request."
    )


def is_ban_blocking(ban: Ban) -> bool:
    """True when a ban row should still block verification."""
    return ban.status == BAN_STATUS_ACTIVE


def decayed_score_multiplier(
    ban: Ban,
    *,
    now: datetime | None = None,
    decay_months: int | None = None,
) -> float:
    """Return 0.0–1.0 weight for a ban's network score contribution after decay."""
    if ban.status != BAN_STATUS_ACTIVE:
        return 0.0
    if ban.category in PERMANENT_NO_DECAY_CATEGORIES:
        return 1.0
    if ban.severity not in _DECAY_SEVERITIES:
        return 1.0
    settings = get_settings()
    months = decay_months if decay_months is not None else settings.ban_decay_months
    cutoff = (now or datetime.now(UTC)) - timedelta(days=months * 30)
    if ban.banned_at <= cutoff:
        return 0.0
    return 1.0


async def local_unban(
    session: AsyncSession,
    chain: ChainClient,
    *,
    ban_id: int | None = None,
    telegram_user_id: int | None = None,
) -> Ban | None:
    """Mark a ban overturned locally and on-chain when configured."""
    if ban_id is not None:
        ban = await session.get(Ban, ban_id)
    elif telegram_user_id is not None:
        ban = await session.scalar(
            select(Ban).where(
                Ban.telegram_user_id == telegram_user_id,
                Ban.status == BAN_STATUS_ACTIVE,
            )
        )
    else:
        return None

    if ban is None:
        return None

    if ban.status != BAN_STATUS_ACTIVE:
        return None

    ban.status = BAN_STATUS_OVERTURNED
    ban.overturned_at = datetime.now(UTC)

    if ban.telegram_user_id is not None:
        profile = await session.scalar(
            select(Profile).where(Profile.telegram_user_id == ban.telegram_user_id)
        )
        if profile is not None and profile.status == "banned":
            profile.status = "approved"

    if ban.chain_tx:
        tx = await chain.overturn_ban(ban.fingerprint_hash, ban.chain_ban_index)
        if tx:
            ban.chain_tx = tx

    await session.commit()
    await session.refresh(ban)
    return ban


async def apply_decay(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    decay_months: int | None = None,
) -> int:
    """Expire low/medium bans older than the configured decay window."""
    settings = get_settings()
    months = decay_months if decay_months is not None else settings.ban_decay_months
    cutoff = (now or datetime.now(UTC)) - timedelta(days=months * 30)
    rows = (
        await session.scalars(select(Ban).where(Ban.status == BAN_STATUS_ACTIVE))
    ).all()
    expired = 0
    for ban in rows:
        if ban.category in PERMANENT_NO_DECAY_CATEGORIES:
            continue
        if ban.severity not in _DECAY_SEVERITIES:
            continue
        if ban.banned_at > cutoff:
            continue
        ban.status = BAN_STATUS_EXPIRED
        expired += 1
    if expired:
        await session.commit()
    return expired


async def create_appeal(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    reason: str,
    ban_id: int | None = None,
    fingerprint_hash: str | None = None,
) -> AppealRecord:
    """Store a pending reinstatement appeal."""
    if ban_id is not None:
        ban = await session.get(Ban, ban_id)
        if ban is not None:
            fingerprint_hash = fingerprint_hash or ban.fingerprint_hash
    appeal = AppealRecord(
        telegram_user_id=telegram_user_id,
        ban_id=ban_id,
        fingerprint_hash=fingerprint_hash,
        reason=reason,
        status=APPEAL_STATUS_PENDING,
    )
    session.add(appeal)
    await session.commit()
    await session.refresh(appeal)
    return appeal
