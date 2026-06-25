"""Tests for standardized ban category and severity taxonomy."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.domain.ban_taxonomy import BanCategory, BanSeverity
from singulr.models import Ban, Profile
from singulr.services.bans import record_ban


def test_ban_category_includes_required_values() -> None:
    """BanCategory covers all standardized network ban labels."""
    expected = {
        "spam",
        "solicitation",
        "scam_fraud",
        "harassment",
        "bot_abuse",
        "impersonation",
        "nsfw",
        "raid_coordination",
        "other",
    }
    assert {member.value for member in BanCategory} == expected


def test_ban_severity_includes_required_tiers() -> None:
    """BanSeverity covers low through permanent tiers."""
    expected = {"low", "medium", "high", "permanent"}
    assert {member.value for member in BanSeverity} == expected


@pytest.mark.asyncio
async def test_record_ban_persists_category_and_severity(db_session: AsyncSession) -> None:
    """record_ban stores category and severity on the ban row."""
    user_id = 8101
    db_session.add(
        Profile(
            telegram_user_id=user_id,
            fingerprint_hash="0x" + "8" * 64,
            keystroke_profile={"rhythm": [1.0]},
            device_type="mobile",
        )
    )
    await db_session.commit()

    await record_ban(
        db_session,
        telegram_user_id=user_id,
        channel_id=42,
        reason="Repeated scam links",
        category=BanCategory.SCAM_FRAUD,
        severity=BanSeverity.PERMANENT,
    )

    ban = await db_session.scalar(select(Ban).where(Ban.telegram_user_id == user_id))
    assert ban is not None
    assert ban.category == BanCategory.SCAM_FRAUD.value
    assert ban.severity == BanSeverity.PERMANENT.value
    assert ban.reason == "Repeated scam links"


@pytest.mark.asyncio
async def test_ban_defaults_for_legacy_style_insert(db_session: AsyncSession) -> None:
    """Ban rows created without explicit taxonomy get sensible defaults."""
    db_session.add(
        Ban(
            telegram_user_id=8102,
            fingerprint_hash="0x" + "9" * 64,
            reason="legacy row",
        )
    )
    await db_session.commit()

    ban = await db_session.scalar(select(Ban).where(Ban.telegram_user_id == 8102))
    assert ban is not None
    assert ban.category == BanCategory.OTHER.value
    assert ban.severity == BanSeverity.MEDIUM.value


@pytest.mark.asyncio
async def test_admin_list_bans_includes_category_and_severity(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Admin ban list exposes category and severity for operator review."""
    db_session.add(
        Ban(
            telegram_user_id=8103,
            fingerprint_hash="0x" + "c" * 64,
            reason="raid",
            category=BanCategory.RAID_COORDINATION.value,
            severity=BanSeverity.HIGH.value,
        )
    )
    await db_session.commit()

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ADMIN_API_KEY", "secret-admin-key")
        from singulr.config import get_settings

        get_settings.cache_clear()
        response = await api_client.get(
            "/api/admin/bans",
            headers={"X-Admin-Key": "secret-admin-key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["category"] == BanCategory.RAID_COORDINATION.value
    assert body[0]["severity"] == BanSeverity.HIGH.value
