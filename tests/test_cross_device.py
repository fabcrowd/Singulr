"""Cross-device fingerprint cross-reference tests.

A user who was banned on one device type (mobile/desktop) must be blocked
when they create a new Telegram account and rejoin from the other device type,
as long as they previously verified on both devices with the original account.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.models import Ban, Profile
from singulr.services.bans import record_ban
from singulr.services.channel_policy import EffectivePolicy
from singulr.services.matching import Decision, check_known_bad
from singulr.domain.ban_taxonomy import BanCategory, BanSeverity
from singulr.services.reverification import get_all_profiles, get_profile, require_reverification


def _policy(**overrides: object) -> EffectivePolicy:
    base = {
        "channel_id": 42,
        "security_preset": "balanced",
        "ban_evasion_auto_deny_threshold": 0.92,
        "local_similarity_flag_threshold": 0.85,
        "network_registry_mode": "off",
        "share_bans_to_network": False,
        "network_auto_reject_categories": [],
        "instant_ban_categories": ["impersonation", "bot_abuse"],
        "social_profiling_enabled": False,
        "social_api_fail_mode": "fail_open",
        "social_pending_score_threshold": 40,
        "social_external_api_enabled": False,
        "admin_ops_chat_id": None,
        "automation_flag_mode": "flag",
        "ai_pending_score_threshold": 50,
    }
    base.update(overrides)
    return EffectivePolicy(**base)  # type: ignore[arg-type]


def _chain_mock() -> MagicMock:
    chain = MagicMock()
    chain.is_banned = AsyncMock(return_value=False)
    chain.get_reputation = AsyncMock(return_value={"score": 0, "active_bans": 0})
    return chain


MOBILE_FP = "0x" + "11" * 32
DESKTOP_FP = "0x" + "22" * 32
NEW_ACCOUNT_MOBILE_FP = "0x" + "33" * 32   # same physical device as MOBILE_FP scenario
NEW_ACCOUNT_DESKTOP_FP = "0x" + "44" * 32


async def _setup_dual_device_user(
    session: AsyncSession,
    telegram_user_id: int = 7001,
) -> None:
    """Simulate a user who verified on both mobile and desktop with the same account."""
    session.add(
        Profile(
            telegram_user_id=telegram_user_id,
            fingerprint_hash=MOBILE_FP,
            keystroke_profile={"device_type": "mobile", "rhythm": [1.0, 1.1, 0.9]},
            device_type="mobile",
            ip_hash="0x" + "aa" * 32,
            status="approved",
        )
    )
    session.add(
        Profile(
            telegram_user_id=telegram_user_id,
            fingerprint_hash=DESKTOP_FP,
            keystroke_profile={"device_type": "desktop", "rhythm": [1.0, 1.05, 0.95]},
            device_type="desktop",
            ip_hash="0x" + "bb" * 32,
            status="approved",
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_dual_device_profiles_stored_separately(db_session: AsyncSession) -> None:
    """A user can have one Profile per device type."""
    await _setup_dual_device_user(db_session, telegram_user_id=7001)
    profiles = await get_all_profiles(db_session, 7001)
    assert len(profiles) == 2
    device_types = {p.device_type for p in profiles}
    assert device_types == {"mobile", "desktop"}


@pytest.mark.asyncio
async def test_get_profile_filters_by_device_type(db_session: AsyncSession) -> None:
    """get_profile(device_type=...) returns the device-specific row."""
    await _setup_dual_device_user(db_session, telegram_user_id=7002)
    mobile = await get_profile(db_session, 7002, device_type="mobile")
    desktop = await get_profile(db_session, 7002, device_type="desktop")
    assert mobile is not None and mobile.fingerprint_hash == MOBILE_FP
    assert desktop is not None and desktop.fingerprint_hash == DESKTOP_FP


@pytest.mark.asyncio
async def test_ban_creates_records_for_all_device_fingerprints(db_session: AsyncSession) -> None:
    """record_ban creates one ban record per device fingerprint for the user."""
    await _setup_dual_device_user(db_session, telegram_user_id=7003)

    await record_ban(
        db_session,
        telegram_user_id=7003,
        channel_id=42,
        reason="ban evasion",
        category=BanCategory.OTHER,
        severity=BanSeverity.HIGH,
    )

    bans = (await db_session.scalars(select(Ban).where(Ban.telegram_user_id == 7003))).all()
    ban_fingerprints = {b.fingerprint_hash for b in bans}
    assert MOBILE_FP in ban_fingerprints, "mobile fingerprint must be in ban records"
    assert DESKTOP_FP in ban_fingerprints, "desktop fingerprint must be in ban records"


@pytest.mark.asyncio
async def test_banned_on_desktop_caught_on_mobile_new_account(db_session: AsyncSession) -> None:
    """A user banned on desktop is blocked when rejoining on mobile from a new account.

    The original account had BOTH mobile and desktop profiles.
    The new account's mobile fingerprint matches the banned mobile fingerprint.
    """
    original_user_id = 7004
    new_account_user_id = 70041

    await _setup_dual_device_user(db_session, telegram_user_id=original_user_id)

    # Ban the original user (creates ban records for BOTH fingerprints)
    await record_ban(
        db_session,
        telegram_user_id=original_user_id,
        channel_id=42,
        reason="rule violation",
    )

    # New account joins from mobile — same physical device as original mobile FP
    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=new_account_user_id,
        fingerprint_hash=MOBILE_FP,   # same device as original mobile session
        ip_hash=None,
        channel_id=42,
        policy=_policy(),
    )

    assert result.decision == Decision.BLOCK
    assert "exact_fingerprint_match" in result.risk_factors


@pytest.mark.asyncio
async def test_banned_on_mobile_caught_on_desktop_new_account(db_session: AsyncSession) -> None:
    """A user banned on mobile is blocked when rejoining on desktop from a new account."""
    original_user_id = 7005
    new_account_user_id = 70051

    await _setup_dual_device_user(db_session, telegram_user_id=original_user_id)

    await record_ban(
        db_session,
        telegram_user_id=original_user_id,
        channel_id=42,
        reason="spam",
    )

    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=new_account_user_id,
        fingerprint_hash=DESKTOP_FP,   # same device as original desktop session
        ip_hash=None,
        channel_id=42,
        policy=_policy(),
    )

    assert result.decision == Decision.BLOCK
    assert "exact_fingerprint_match" in result.risk_factors


@pytest.mark.asyncio
async def test_single_device_user_ban_only_registers_one_fingerprint(
    db_session: AsyncSession,
) -> None:
    """A user who only verified on desktop gets exactly one ban record."""
    db_session.add(
        Profile(
            telegram_user_id=7006,
            fingerprint_hash=DESKTOP_FP,
            keystroke_profile={"device_type": "desktop", "rhythm": []},
            device_type="desktop",
            status="approved",
        )
    )
    await db_session.commit()

    await record_ban(db_session, telegram_user_id=7006, channel_id=42, reason="spam")

    bans = (await db_session.scalars(select(Ban).where(Ban.telegram_user_id == 7006))).all()
    assert len(bans) == 1
    assert bans[0].fingerprint_hash == DESKTOP_FP


@pytest.mark.asyncio
async def test_require_reverification_flags_all_device_profiles(db_session: AsyncSession) -> None:
    """require_reverification marks both mobile and desktop profiles."""
    await _setup_dual_device_user(db_session, telegram_user_id=7007)

    result = await require_reverification(db_session, 7007)
    assert result is not None

    profiles = await get_all_profiles(db_session, 7007)
    assert all(p.status == "reverification_required" for p in profiles)


@pytest.mark.asyncio
async def test_clean_user_on_unrelated_device_is_approved(db_session: AsyncSession) -> None:
    """A genuinely new user on a different device gets approved (no false positive)."""
    original_user_id = 7008
    unrelated_user_id = 70081
    unrelated_fp = "0x" + "ff" * 32   # completely different device

    await _setup_dual_device_user(db_session, telegram_user_id=original_user_id)
    await record_ban(db_session, telegram_user_id=original_user_id, channel_id=42, reason="spam")

    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=unrelated_user_id,
        fingerprint_hash=unrelated_fp,
        ip_hash=None,
        channel_id=42,
        policy=_policy(),
    )

    assert result.decision == Decision.APPROVE
