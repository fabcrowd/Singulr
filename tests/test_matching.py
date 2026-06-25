"""Unit tests for known-bad registry matching."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.models import Ban, IPSession, Profile
from singulr.services.channel_policy import EffectivePolicy
from singulr.services.keystroke import build_keystroke_profile, keystroke_similarity
from singulr.services.matching import Decision, check_known_bad

_SAMPLE_KEYSTROKES = [
    {"key": "W", "down": 0, "up": 80, "flight": 0},
    {"key": "e", "down": 120, "up": 190, "flight": 40},
    {"key": "l", "down": 250, "up": 310, "flight": 60},
]

_BANNED_KEYSTROKES = [
    {"key": "W", "down": 0, "up": 80, "flight": 0},
    {"key": "e", "down": 120, "up": 190, "flight": 40},
    {"key": "l", "down": 250, "up": 310, "flight": 60},
    {"key": "c", "down": 380, "up": 450, "flight": 70},
    {"key": "o", "down": 520, "up": 590, "flight": 70},
    {"key": "m", "down": 660, "up": 730, "flight": 70},
    {"key": "e", "down": 800, "up": 870, "flight": 70},
    {"key": "!", "down": 940, "up": 1010, "flight": 70},
]

_MEDIUM_SIM_KEYSTROKES = [
    {"key": "W", "down": 0, "up": 80, "flight": 0},
    {"key": "e", "down": 200, "up": 270, "flight": 120},
    {"key": "l", "down": 450, "up": 520, "flight": 180},
    {"key": "c", "down": 700, "up": 770, "flight": 30},
    {"key": "o", "down": 850, "up": 920, "flight": 150},
    {"key": "m", "down": 1100, "up": 1170, "flight": 50},
    {"key": "e", "down": 1300, "up": 1370, "flight": 200},
    {"key": "!", "down": 1600, "up": 1670, "flight": 80},
]

_DEFAULT_POLICY = EffectivePolicy(
    channel_id=42,
    security_preset="balanced",
    ban_evasion_auto_deny_threshold=0.92,
    local_similarity_flag_threshold=0.85,
    network_registry_mode="read",
    share_bans_to_network=False,
    network_auto_reject_categories=["scam_fraud", "raid_coordination"],
    instant_ban_categories=["impersonation", "bot_abuse"],
    social_profiling_enabled=True,
    social_api_fail_mode="fail_open",
    social_pending_score_threshold=40,
    admin_ops_chat_id=None,
)


def _chain_mock(*, banned: bool = False) -> MagicMock:
    chain = MagicMock()
    chain.is_banned = AsyncMock(return_value=banned)
    chain.get_reputation = AsyncMock(return_value={"score": 0, "active_bans": 0})
    return chain


@pytest.mark.asyncio
async def test_blocks_known_banned_user_id(db_session: AsyncSession) -> None:
    """Exact telegram user id match blocks immediately."""
    db_session.add(
        Ban(
            telegram_user_id=111,
            fingerprint_hash="0x" + "a" * 64,
            reason="spam",
        )
    )
    await db_session.commit()

    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=111,
        fingerprint_hash="0x" + "b" * 64,
        ip_hash=None,
    )

    assert result.decision == Decision.BLOCK
    assert "exact_user_id_match" in result.risk_factors


@pytest.mark.asyncio
async def test_blocks_known_banned_fingerprint(db_session: AsyncSession) -> None:
    """Exact fingerprint hash match blocks even for a new user id."""
    fingerprint = "0x" + "c" * 64
    db_session.add(
        Ban(
            telegram_user_id=9001,
            fingerprint_hash=fingerprint,
            reason="prior_ban",
        )
    )
    await db_session.commit()

    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=9002,
        fingerprint_hash=fingerprint,
        ip_hash=None,
    )

    assert result.decision == Decision.BLOCK
    assert "exact_fingerprint_match" in result.risk_factors


@pytest.mark.asyncio
async def test_approves_clean_user(db_session: AsyncSession) -> None:
    """Users with no ban signals are approved."""
    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=333,
        fingerprint_hash="0x" + "d" * 64,
        ip_hash=None,
    )

    assert result.decision == Decision.APPROVE
    assert result.reason == "Clean"
    assert result.risk_factors == []


@pytest.mark.asyncio
async def test_blocks_high_keystroke_ban_evasion_on_new_user_id(db_session: AsyncSession) -> None:
    """High keystroke similarity to a banned profile on a new user id auto-denies."""
    fingerprint = "0x" + "e" * 64
    banned_profile = build_keystroke_profile(_BANNED_KEYSTROKES, "desktop")
    evasion_profile = build_keystroke_profile(_BANNED_KEYSTROKES, "desktop")
    assert keystroke_similarity(banned_profile, evasion_profile) >= 0.92
    db_session.add(
        Ban(
            telegram_user_id=8001,
            fingerprint_hash=fingerprint,
            reason="banned",
        )
    )
    db_session.add(
        Profile(
            telegram_user_id=8001,
            fingerprint_hash=fingerprint,
            keystroke_profile=banned_profile,
            device_type="desktop",
        )
    )
    await db_session.commit()

    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=8002,
        fingerprint_hash="0x" + "f" * 64,
        ip_hash=None,
        keystroke_profile=evasion_profile,
        policy=_DEFAULT_POLICY,
    )

    assert result.decision == Decision.BLOCK
    assert any("keystroke_similarity" in factor for factor in result.risk_factors)


@pytest.mark.asyncio
async def test_pending_medium_keystroke_ban_evasion_on_new_user_id(db_session: AsyncSession) -> None:
    """Medium similarity to a banned profile yields pending review, not auto-deny."""
    fingerprint = "0x" + "e1" * 32
    banned_profile = build_keystroke_profile(_BANNED_KEYSTROKES, "desktop")
    evasion_profile = build_keystroke_profile(_MEDIUM_SIM_KEYSTROKES, "desktop")
    score = keystroke_similarity(banned_profile, evasion_profile)
    assert 0.85 <= score < 0.92
    db_session.add(
        Ban(
            telegram_user_id=8011,
            fingerprint_hash=fingerprint,
            reason="banned",
        )
    )
    db_session.add(
        Profile(
            telegram_user_id=8011,
            fingerprint_hash=fingerprint,
            keystroke_profile=banned_profile,
            device_type="desktop",
        )
    )
    await db_session.commit()

    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=8012,
        fingerprint_hash="0x" + "f1" * 32,
        ip_hash=None,
        keystroke_profile=evasion_profile,
        policy=_DEFAULT_POLICY,
    )

    assert result.decision == Decision.PENDING
    assert result.decision != Decision.BLOCK
    assert any("keystroke_similarity" in factor for factor in result.risk_factors)


@pytest.mark.asyncio
async def test_flags_keystroke_similarity_to_banned_profile(db_session: AsyncSession) -> None:
    """Legacy short-sample keystroke match auto-denies under dual-threshold policy."""
    fingerprint = "0x" + "e" * 64
    keystroke_profile = build_keystroke_profile(_SAMPLE_KEYSTROKES, "desktop")
    db_session.add(
        Ban(
            telegram_user_id=8001,
            fingerprint_hash=fingerprint,
            reason="banned",
        )
    )
    db_session.add(
        Profile(
            telegram_user_id=8001,
            fingerprint_hash=fingerprint,
            keystroke_profile=keystroke_profile,
            device_type="desktop",
        )
    )
    await db_session.commit()

    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=8002,
        fingerprint_hash="0x" + "f" * 64,
        ip_hash=None,
        keystroke_profile=keystroke_profile,
        policy=_DEFAULT_POLICY,
    )

    assert result.decision == Decision.BLOCK
    assert any("keystroke_similarity" in factor for factor in result.risk_factors)


@pytest.mark.asyncio
async def test_blocks_on_chain_blacklist(db_session: AsyncSession) -> None:
    """On-chain ban registry sends cross-channel hits to pending review."""
    fingerprint = "0x" + "11" * 32
    chain = _chain_mock(banned=True)

    result = await check_known_bad(
        db_session,
        chain,
        telegram_user_id=4444,
        fingerprint_hash=fingerprint,
        ip_hash=None,
    )

    assert result.decision == Decision.PENDING
    assert "chain_blacklist" in result.risk_factors
    chain.is_banned.assert_awaited_once_with(fingerprint)


@pytest.mark.asyncio
async def test_flags_ip_velocity_multi_account_same_ip(db_session: AsyncSession) -> None:
    """Same IP verifying multiple accounts within 24h is flagged."""
    ip_hash = "0x" + "22" * 32
    now = datetime.now(UTC)
    db_session.add(
        IPSession(
            ip_hash=ip_hash,
            telegram_user_id=1001,
            channel_id=42,
            action="verify",
            timestamp=now,
        )
    )
    db_session.add(
        IPSession(
            ip_hash=ip_hash,
            telegram_user_id=1002,
            channel_id=42,
            action="verify",
            timestamp=now,
        )
    )
    await db_session.commit()

    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=1003,
        fingerprint_hash="0x" + "33" * 32,
        ip_hash=ip_hash,
    )

    assert result.decision == Decision.FLAG
    assert "ip_velocity" in result.risk_factors


@pytest.mark.asyncio
async def test_social_hard_category_instant_ban(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hard social category in instant_ban list blocks immediately."""
    monkeypatch.setenv("SOCIAL_PROFILE_PROVIDER", "mock")
    monkeypatch.setenv("MOCK_SOCIAL_HARD_USER_IDS", "7777")
    from singulr.config import get_settings

    get_settings.cache_clear()

    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=7777,
        fingerprint_hash="0x" + "44" * 32,
        ip_hash=None,
        channel_id=42,
        policy=_DEFAULT_POLICY,
    )

    assert result.decision == Decision.BLOCK
    assert any("social_hard" in factor for factor in result.risk_factors)
