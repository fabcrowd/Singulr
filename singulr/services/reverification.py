"""Admin-triggered member reverification."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.models import Profile

STATUS_REVERIFICATION_REQUIRED = "reverification_required"
STATUS_APPROVED = "approved"


async def get_profile(
    session: AsyncSession,
    telegram_user_id: int,
    device_type: str | None = None,
) -> Profile | None:
    """Load a member profile by Telegram user id, optionally filtered by device type."""
    query = select(Profile).where(Profile.telegram_user_id == telegram_user_id)
    if device_type is not None:
        query = query.where(Profile.device_type == device_type)
    return await session.scalar(query)


async def get_all_profiles(session: AsyncSession, telegram_user_id: int) -> list[Profile]:
    """Return all device-type profiles for a Telegram user (mobile + desktop)."""
    rows = await session.scalars(
        select(Profile).where(Profile.telegram_user_id == telegram_user_id)
    )
    return list(rows.all())


async def require_reverification(session: AsyncSession, telegram_user_id: int) -> Profile | None:
    """Flag all device profiles for mandatory reverification; returns one profile or None."""
    profiles = await get_all_profiles(session, telegram_user_id)
    if not profiles:
        return None
    for profile in profiles:
        profile.status = STATUS_REVERIFICATION_REQUIRED
    await session.commit()
    return profiles[0]


def is_reverification_required(profile: Profile | None) -> bool:
    """True when the profile must complete verification again."""
    return profile is not None and profile.status == STATUS_REVERIFICATION_REQUIRED
