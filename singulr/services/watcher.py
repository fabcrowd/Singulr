"""Periodic watcher — compare member stylometry against banned profiles."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.config import get_settings
from singulr.models import Ban, Profile, StylometryProfile
from singulr.services.stylometry import stylometry_similarity

logger = logging.getLogger(__name__)


async def find_watcher_matches(session: AsyncSession) -> list[dict]:
    """Return likely matches between active members and banned stylometry."""
    settings = get_settings()
    bans = (await session.scalars(select(Ban))).all()
    if not bans:
        return []

    banned_user_ids = {b.telegram_user_id for b in bans if b.telegram_user_id}

    profiles = (await session.scalars(select(StylometryProfile))).all()
    matches: list[dict] = []

    for member in profiles:
        if member.telegram_user_id in banned_user_ids:
            continue
        if member.message_count < 5:
            continue

        for ban in bans:
            ban_profile = await session.scalar(
                select(Profile).where(Profile.fingerprint_hash == ban.fingerprint_hash)
            )
            if not ban_profile:
                continue
            ban_stylo = await session.get(StylometryProfile, ban_profile.telegram_user_id)
            if not ban_stylo or ban_stylo.message_count < 5:
                continue

            score = stylometry_similarity(member.feature_vector, ban_stylo.feature_vector)
            if score >= settings.stylometry_similarity_threshold:
                matches.append(
                    {
                        "user_id": member.telegram_user_id,
                        "ban_fingerprint": ban.fingerprint_hash,
                        "score": score,
                        "reason": "stylometry_match",
                    }
                )
                break

    logger.info("Watcher found %d potential matches", len(matches))
    return matches
