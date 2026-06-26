"""Unit tests for known-bad registry matching."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.models import Ban, IPSession, Profile, StylometryProfile
from singulr.config import get_settings
from singulr.services.channel_policy import EffectivePolicy
from singulr.services.join_velocity import record_join_request, reset_join_velocity_tracker
from singulr.services.keystroke import build_keystroke_profile, keystroke_similarity
from singulr.services.matching import Decision, check_known_bad
from singulr.services.stylometry import extract_features, merge_feature_vectors, stylometry_similarity

_AUTHOR_A_MESSAGES = [
    "lol yeah",
    "nah idk",
    "whatever man",
    "yeah sure lol",
]
_MEDIUM_STYLO_MESSAGES = ["nah", "idk"]


def _merged_stylometry(messages: list[str]) -> dict[str, float]:
    """Build an averaged stylometry vector from sample messages."""
    return merge_feature_vectors([extract_features(message) for message in messages])

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
    social_external_api_enabled=False,
    admin_ops_chat_id=None,
    automation_flag_mode="flag",
    ai_pending_score_threshold=50,
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
async def test_join_burst_adds_risk_factor_at_verify(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """High join velocity during a burst adds a join_burst risk factor."""
    monkeypatch.setenv("JOIN_BURST_THRESHOLD", "2")
    get_settings.cache_clear()
    reset_join_velocity_tracker()
    channel_id = -100200
    record_join_request(channel_id)
    record_join_request(channel_id)

    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=333,
        fingerprint_hash="0x" + "d" * 64,
        ip_hash=None,
        channel_id=channel_id,
        policy=_DEFAULT_POLICY,
    )

    assert "join_burst:2" in result.risk_factors
    assert result.decision == Decision.FLAG


@pytest.mark.asyncio
async def test_webdriver_forces_pending_under_strict_automation_mode(
    db_session: AsyncSession,
) -> None:
    """Webdriver with pending automation policy escalates to admin review."""
    from dataclasses import replace

    policy = replace(
        _DEFAULT_POLICY,
        security_preset="strict",
        automation_flag_mode="pending",
        ai_pending_score_threshold=25,
    )

    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=334,
        fingerprint_hash="0x" + "f" * 64,
        ip_hash=None,
        env_flags={"webdriver": True, "headless_ua": False},
        policy=policy,
    )

    assert result.decision == Decision.PENDING
    assert "automation_score:30" in result.risk_factors
    assert result.reason == "Automation review required"


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
async def test_blocks_high_stylometry_ban_evasion_on_new_user_id(db_session: AsyncSession) -> None:
    """High stylometry similarity to a banned writer on a new user id auto-denies."""
    fingerprint = "0x" + "s1" * 32
    banned_vector = _merged_stylometry(_AUTHOR_A_MESSAGES)
    evasion_vector = banned_vector
    assert stylometry_similarity(banned_vector, evasion_vector) >= 0.92
    db_session.add(
        Ban(
            telegram_user_id=8101,
            fingerprint_hash=fingerprint,
            stylometry_hash="0x" + "aa" * 32,
            reason="banned",
        )
    )
    db_session.add(
        StylometryProfile(
            telegram_user_id=8101,
            feature_vector=banned_vector,
            message_count=len(_AUTHOR_A_MESSAGES),
        )
    )
    await db_session.commit()

    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=8102,
        fingerprint_hash="0x" + "f2" * 32,
        ip_hash=None,
        stylometry_vector=evasion_vector,
        policy=_DEFAULT_POLICY,
    )

    assert result.decision == Decision.BLOCK
    assert any("stylometry_similarity" in factor for factor in result.risk_factors)


@pytest.mark.asyncio
async def test_pending_medium_stylometry_ban_evasion_on_new_user_id(db_session: AsyncSession) -> None:
    """Medium stylometry similarity yields pending review, not auto-deny."""
    fingerprint = "0x" + "s2" * 32
    banned_vector = _merged_stylometry(_AUTHOR_A_MESSAGES)
    evasion_vector = _merged_stylometry(_MEDIUM_STYLO_MESSAGES)
    score = stylometry_similarity(banned_vector, evasion_vector)
    policy = replace(_DEFAULT_POLICY, ban_evasion_auto_deny_threshold=0.95)
    assert policy.local_similarity_flag_threshold <= score < policy.ban_evasion_auto_deny_threshold
    db_session.add(
        Ban(
            telegram_user_id=8111,
            fingerprint_hash=fingerprint,
            stylometry_hash="0x" + "bb" * 32,
            reason="banned",
        )
    )
    db_session.add(
        StylometryProfile(
            telegram_user_id=8111,
            feature_vector=banned_vector,
            message_count=len(_AUTHOR_A_MESSAGES),
        )
    )
    await db_session.commit()

    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=8112,
        fingerprint_hash="0x" + "f3" * 32,
        ip_hash=None,
        stylometry_vector=evasion_vector,
        policy=policy,
    )

    assert result.decision == Decision.PENDING
    assert result.decision != Decision.BLOCK
    assert any("stylometry_similarity" in factor for factor in result.risk_factors)


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
