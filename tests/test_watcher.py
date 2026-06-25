"""Integration tests for the in-channel stylometry watcher."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.models import Ban, Profile, StylometryProfile
from singulr.services.stylometry import extract_features, merge_feature_vectors
from singulr.services.watcher import find_watcher_matches

_BANNED_MESSAGES = [
    "lol yeah",
    "nah idk",
    "whatever man",
    "yeah sure lol",
    "lol nah",
    "idk yeah",
]

_MEMBER_MESSAGES = [
    "lol yeah",
    "nah idk",
    "whatever man",
    "yeah sure lol",
    "lol nah",
    "idk yeah",
]


def _profile_vector(messages: list[str]) -> dict[str, float]:
    return merge_feature_vectors([extract_features(message) for message in messages])


@pytest.mark.asyncio
async def test_find_watcher_matches_returns_stylometry_hit(db_session: AsyncSession) -> None:
    """Watcher flags a member whose writing style matches a banned user."""
    banned_user_id = 9001
    member_user_id = 5000
    fingerprint = "0x" + "aa" * 32

    db_session.add(
        Ban(
            telegram_user_id=banned_user_id,
            fingerprint_hash=fingerprint,
            reason="banned",
        )
    )
    db_session.add(
        Profile(
            telegram_user_id=banned_user_id,
            fingerprint_hash=fingerprint,
            keystroke_profile={},
            device_type="desktop",
        )
    )
    db_session.add(
        StylometryProfile(
            telegram_user_id=banned_user_id,
            feature_vector=_profile_vector(_BANNED_MESSAGES),
            message_count=6,
        )
    )
    db_session.add(
        StylometryProfile(
            telegram_user_id=member_user_id,
            feature_vector=_profile_vector(_MEMBER_MESSAGES),
            message_count=6,
        )
    )
    await db_session.commit()

    matches = await find_watcher_matches(db_session)

    assert len(matches) >= 1
    assert matches[0]["user_id"] == member_user_id
    assert matches[0]["ban_fingerprint"] == fingerprint
    assert matches[0]["reason"] == "stylometry_match"


@pytest.mark.asyncio
async def test_find_watcher_matches_empty_when_no_bans(db_session: AsyncSession) -> None:
    """Watcher returns no matches when the ban registry is empty."""
    db_session.add(
        StylometryProfile(
            telegram_user_id=5001,
            feature_vector=_profile_vector(_MEMBER_MESSAGES),
            message_count=6,
        )
    )
    await db_session.commit()

    matches = await find_watcher_matches(db_session)

    assert matches == []


@pytest.mark.asyncio
async def test_find_watcher_matches_skips_members_with_few_messages(
    db_session: AsyncSession,
) -> None:
    """Members below the message-count floor are not compared."""
    banned_user_id = 9002
    member_user_id = 5002
    fingerprint = "0x" + "bb" * 32

    db_session.add(
        Ban(
            telegram_user_id=banned_user_id,
            fingerprint_hash=fingerprint,
            reason="banned",
        )
    )
    db_session.add(
        Profile(
            telegram_user_id=banned_user_id,
            fingerprint_hash=fingerprint,
            keystroke_profile={},
            device_type="desktop",
        )
    )
    db_session.add(
        StylometryProfile(
            telegram_user_id=banned_user_id,
            feature_vector=_profile_vector(_BANNED_MESSAGES),
            message_count=6,
        )
    )
    db_session.add(
        StylometryProfile(
            telegram_user_id=member_user_id,
            feature_vector=_profile_vector(_MEMBER_MESSAGES),
            message_count=2,
        )
    )
    await db_session.commit()

    matches = await find_watcher_matches(db_session)

    assert matches == []


@pytest.mark.asyncio
async def test_find_watcher_matches_ignores_overturned_bans(db_session: AsyncSession) -> None:
    """Overturned bans are excluded from watcher comparisons."""
    banned_user_id = 9003
    member_user_id = 5003
    fingerprint = "0x" + "cc" * 32

    db_session.add(
        Ban(
            telegram_user_id=banned_user_id,
            fingerprint_hash=fingerprint,
            reason="mistake",
            status="overturned",
        )
    )
    db_session.add(
        Profile(
            telegram_user_id=banned_user_id,
            fingerprint_hash=fingerprint,
            keystroke_profile={},
            device_type="desktop",
        )
    )
    db_session.add(
        StylometryProfile(
            telegram_user_id=banned_user_id,
            feature_vector=_profile_vector(_BANNED_MESSAGES),
            message_count=6,
        )
    )
    db_session.add(
        StylometryProfile(
            telegram_user_id=member_user_id,
            feature_vector=_profile_vector(_MEMBER_MESSAGES),
            message_count=6,
        )
    )
    await db_session.commit()

    matches = await find_watcher_matches(db_session)

    assert matches == []
