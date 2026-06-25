"""Unit tests for known-bad registry matching."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.models import Ban, IPSession, Profile
from singulr.services.keystroke import build_keystroke_profile
from singulr.services.matching import Decision, check_known_bad

_SAMPLE_KEYSTROKES = [
    {"key": "W", "down": 0, "up": 80, "flight": 0},
    {"key": "e", "down": 120, "up": 190, "flight": 40},
    {"key": "l", "down": 250, "up": 310, "flight": 60},
]


def _chain_mock(*, banned: bool = False) -> MagicMock:
    chain = MagicMock()
    chain.is_banned = AsyncMock(return_value=banned)
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
async def test_flags_keystroke_similarity_to_banned_profile(db_session: AsyncSession) -> None:
    """High keystroke similarity against a banned profile yields FLAG."""
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
    )

    assert result.decision == Decision.FLAG
    assert any("keystroke_similarity" in factor for factor in result.risk_factors)


@pytest.mark.asyncio
async def test_blocks_on_chain_blacklist(db_session: AsyncSession) -> None:
    """On-chain ban registry blocks before local similarity checks."""
    fingerprint = "0x" + "11" * 32
    chain = _chain_mock(banned=True)

    result = await check_known_bad(
        db_session,
        chain,
        telegram_user_id=4444,
        fingerprint_hash=fingerprint,
        ip_hash=None,
    )

    assert result.decision == Decision.BLOCK
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
