"""Tests for admin ban persistence."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.models import Ban, Profile, StylometryProfile
from singulr.services.bans import record_ban


@pytest.mark.asyncio
async def test_persist_ban_stores_stylometry_hash(db_session: AsyncSession) -> None:
    """Admin ban records stylometry_hash when profile exists."""
    user_id = 7001
    db_session.add(
        Profile(
            telegram_user_id=user_id,
            fingerprint_hash="0x" + "7" * 64,
            keystroke_profile={"rhythm": [1.0, 1.1]},
            device_type="desktop",
        )
    )
    db_session.add(
        StylometryProfile(
            telegram_user_id=user_id,
            feature_vector={"avg_word_len": 4.2, "msg_len": 42.0},
            message_count=10,
        )
    )
    await db_session.commit()

    await record_ban(
        db_session,
        telegram_user_id=user_id,
        channel_id=1,
        reason="admin_test",
    )

    ban = await db_session.scalar(select(Ban).where(Ban.telegram_user_id == user_id))
    assert ban is not None
    assert ban.stylometry_hash is not None
    assert ban.stylometry_hash.startswith("0x")
