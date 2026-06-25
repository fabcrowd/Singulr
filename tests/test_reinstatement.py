"""Tests for hybrid reinstatement flows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.domain.ban_taxonomy import BanCategory, BanSeverity
from singulr.models import AppealRecord, Ban, Profile
from singulr.services.matching import Decision, check_known_bad
from singulr.services.reinstatement import (
    BAN_STATUS_ACTIVE,
    BAN_STATUS_EXPIRED,
    BAN_STATUS_OVERTURNED,
    apply_decay,
    create_appeal,
    decayed_score_multiplier,
    local_unban,
)


@pytest.mark.asyncio
async def test_local_unban_marks_overturned_and_calls_chain(db_session: AsyncSession) -> None:
    """Overturn updates status and calls chain when chain_tx is set."""
    ban = Ban(
        telegram_user_id=91001,
        fingerprint_hash="0x" + "a" * 64,
        reason="mistake",
        chain_tx="0xdead",
        chain_ban_index=0,
        status=BAN_STATUS_ACTIVE,
    )
    db_session.add(ban)
    db_session.add(
        Profile(
            telegram_user_id=91001,
            fingerprint_hash=ban.fingerprint_hash,
            keystroke_profile={"rhythm": [1.0]},
            device_type="mobile",
            status="banned",
        )
    )
    await db_session.commit()

    chain = MagicMock()
    chain.is_banned = AsyncMock(return_value=False)
    chain.get_reputation = AsyncMock(return_value={"score": 0, "active_bans": 0})
    chain.overturn_ban = AsyncMock(return_value="0xbeef")

    result = await local_unban(db_session, chain, ban_id=ban.id)

    assert result is not None
    assert result.status == BAN_STATUS_OVERTURNED
    assert result.overturned_at is not None
    chain.overturn_ban.assert_awaited_once_with(ban.fingerprint_hash, 0)
    profile = await db_session.scalar(select(Profile).where(Profile.telegram_user_id == 91001))
    assert profile is not None
    assert profile.status == "approved"

    row = await db_session.get(Ban, ban.id)
    assert row is not None
    assert row.status == BAN_STATUS_OVERTURNED


@pytest.mark.asyncio
async def test_overturned_ban_allows_verify(db_session: AsyncSession) -> None:
    """User with overturned ban is not blocked by local ban checks."""
    fingerprint = "0x" + "b" * 64
    ban = Ban(
        telegram_user_id=91002,
        fingerprint_hash=fingerprint,
        status=BAN_STATUS_OVERTURNED,
        overturned_at=datetime.now(UTC),
    )
    db_session.add(ban)
    await db_session.commit()

    chain = MagicMock()
    chain.is_banned = AsyncMock(return_value=False)
    chain.get_reputation = AsyncMock(return_value={"score": 0, "active_bans": 0})

    result = await check_known_bad(
        db_session,
        chain,
        telegram_user_id=91002,
        fingerprint_hash=fingerprint,
        ip_hash=None,
    )

    assert result.decision == Decision.APPROVE


@pytest.mark.asyncio
async def test_apply_decay_expires_old_low_medium_bans(db_session: AsyncSession) -> None:
    """Low/medium bans older than decay window become expired."""
    old = datetime.now(UTC) - timedelta(days=200)
    ban = Ban(
        telegram_user_id=91003,
        fingerprint_hash="0x" + "c" * 64,
        category=BanCategory.SPAM.value,
        severity=BanSeverity.LOW.value,
        status=BAN_STATUS_ACTIVE,
    )
    db_session.add(ban)
    await db_session.commit()
    ban.banned_at = old
    await db_session.commit()

    expired_count = await apply_decay(db_session, now=datetime.now(UTC), decay_months=6)

    assert expired_count == 1
    refreshed = await db_session.get(Ban, ban.id)
    assert refreshed is not None
    assert refreshed.status == BAN_STATUS_EXPIRED


@pytest.mark.asyncio
async def test_apply_decay_skips_permanent_categories(db_session: AsyncSession) -> None:
    """Scam/raid categories never auto-decay."""
    old = datetime.now(UTC) - timedelta(days=400)
    ban = Ban(
        telegram_user_id=91004,
        fingerprint_hash="0x" + "d" * 64,
        category=BanCategory.SCAM_FRAUD.value,
        severity=BanSeverity.MEDIUM.value,
        status=BAN_STATUS_ACTIVE,
    )
    db_session.add(ban)
    await db_session.commit()
    ban.banned_at = old
    await db_session.commit()

    expired_count = await apply_decay(db_session, now=datetime.now(UTC), decay_months=6)

    assert expired_count == 0
    refreshed = await db_session.get(Ban, ban.id)
    assert refreshed is not None
    assert refreshed.status == BAN_STATUS_ACTIVE


def test_decayed_score_multiplier_zero_after_window() -> None:
    """Score contribution drops to zero once decay window elapses."""
    ban = Ban(
        telegram_user_id=91005,
        fingerprint_hash="0x" + "e" * 64,
        category=BanCategory.HARASSMENT.value,
        severity=BanSeverity.MEDIUM.value,
        status=BAN_STATUS_ACTIVE,
        banned_at=datetime.now(UTC) - timedelta(days=200),
    )
    assert decayed_score_multiplier(ban, now=datetime.now(UTC), decay_months=6) == 0.0


@pytest.mark.asyncio
async def test_create_appeal_persists_pending_record(db_session: AsyncSession) -> None:
    """Appeal stub stores pending status."""
    appeal = await create_appeal(
        db_session,
        telegram_user_id=91006,
        reason="false positive",
        ban_id=None,
        fingerprint_hash="0x" + "f" * 64,
    )

    assert appeal.status == "pending"
    row = await db_session.get(AppealRecord, appeal.id)
    assert row is not None
    assert row.reason == "false positive"


@pytest.mark.asyncio
async def test_admin_appeals_endpoint_creates_record(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST /api/admin/appeals with admin key creates appeal."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ADMIN_API_KEY", "secret-admin-key")
        from singulr.config import get_settings

        get_settings.cache_clear()
        response = await api_client.post(
            "/api/admin/appeals",
            headers={"X-Admin-Key": "secret-admin-key"},
            json={"telegram_user_id": 91007, "reason": "appeal via api"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["status"] == "pending"

    row = await db_session.scalar(
        select(AppealRecord).where(AppealRecord.telegram_user_id == 91007)
    )
    assert row is not None


@pytest.mark.asyncio
async def test_local_unban_inactive_ban_id_returns_none(db_session: AsyncSession) -> None:
    """Unban by overturned ban_id does not report success."""
    ban = Ban(
        telegram_user_id=91008,
        fingerprint_hash="0x" + "8" * 64,
        status=BAN_STATUS_OVERTURNED,
        overturned_at=datetime.now(UTC),
    )
    db_session.add(ban)
    await db_session.commit()

    chain = MagicMock()
    result = await local_unban(db_session, chain, ban_id=ban.id)
    assert result is None


@pytest.mark.asyncio
async def test_record_ban_reactivates_overturned_row(db_session: AsyncSession) -> None:
    """Re-ban after overturn reactivates the existing ban row."""
    from singulr.domain.ban_taxonomy import BanCategory, BanSeverity
    from singulr.services.bans import record_ban

    fingerprint = "0x" + "9" * 64
    db_session.add(
        Profile(
            telegram_user_id=91009,
            fingerprint_hash=fingerprint,
            keystroke_profile={"rhythm": [1.0]},
            device_type="mobile",
        )
    )
    db_session.add(
        Ban(
            telegram_user_id=91009,
            fingerprint_hash=fingerprint,
            status=BAN_STATUS_OVERTURNED,
            overturned_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TRUSTED_CHANNEL_IDS", "1")
        from singulr.config import get_settings

        get_settings.cache_clear()
        await record_ban(
            db_session,
            telegram_user_id=91009,
            channel_id=1,
            category=BanCategory.SPAM,
            severity=BanSeverity.LOW,
        )

    row = await db_session.scalar(select(Ban).where(Ban.fingerprint_hash == fingerprint))
    assert row is not None
    assert row.status == BAN_STATUS_ACTIVE
    assert row.overturned_at is None
