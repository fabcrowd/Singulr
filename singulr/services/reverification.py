"""Admin-triggered member reverification."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.models import Profile

STATUS_REVERIFICATION_REQUIRED = "reverification_required"
STATUS_APPROVED = "approved"


async def get_profile(session: AsyncSession, telegram_user_id: int) -> Profile | None:
    """Load a member profile by Telegram user id."""
    return await session.scalar(
        select(Profile).where(Profile.telegram_user_id == telegram_user_id)
    )


async def require_reverification(session: AsyncSession, telegram_user_id: int) -> Profile | None:
    """Flag an existing profile for mandatory reverification."""
    profile = await get_profile(session, telegram_user_id)
    if not profile:
        return None
    profile.status = STATUS_REVERIFICATION_REQUIRED
    await session.commit()
    return profile


def is_reverification_required(profile: Profile | None) -> bool:
    """True when the profile must complete verification again."""
    return profile is not None and profile.status == STATUS_REVERIFICATION_REQUIRED
