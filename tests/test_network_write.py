"""Tests for network ban write path."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.domain.ban_taxonomy import BanCategory, BanSeverity
from singulr.models import ChannelSecuritySettings, Profile
from singulr.services.bans import record_ban, should_contribute_to_network
from singulr.services.channel_policy import EffectivePolicy


def _write_policy(**overrides: object) -> EffectivePolicy:
    base = {
        "channel_id": 100,
        "security_preset": "balanced",
        "ban_evasion_auto_deny_threshold": 0.92,
        "local_similarity_flag_threshold": 0.85,
        "network_registry_mode": "read_write",
        "share_bans_to_network": True,
        "network_auto_reject_categories": ["scam_fraud"],
        "instant_ban_categories": ["impersonation", "bot_abuse"],
        "social_profiling_enabled": True,
        "social_api_fail_mode": "fail_open",
        "social_pending_score_threshold": 40,
        "social_external_api_enabled": False,
        "admin_ops_chat_id": None,
    }
    base.update(overrides)
    return EffectivePolicy(**base)  # type: ignore[arg-type]


def test_untrusted_channel_skips_network_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """Untrusted channel with trusted list configured does not contribute."""
    monkeypatch.setenv("TRUSTED_CHANNEL_IDS", "200,201")
    from singulr.config import get_settings

    get_settings.cache_clear()
    policy = _write_policy(channel_id=100)
    assert should_contribute_to_network(100, policy) is False


def test_trusted_read_write_channel_contributes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trusted channel in read_write mode contributes to network."""
    monkeypatch.setenv("TRUSTED_CHANNEL_IDS", "100")
    from singulr.config import get_settings

    get_settings.cache_clear()
    policy = _write_policy(channel_id=100)
    assert should_contribute_to_network(100, policy) is True


@pytest.mark.asyncio
async def test_record_ban_writes_chain_for_trusted_channel(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trusted channel ban triggers chain record_ban."""
    monkeypatch.setenv("TRUSTED_CHANNEL_IDS", "55")
    from singulr.config import get_settings

    get_settings.cache_clear()
    db_session.add(
        ChannelSecuritySettings(
            channel_id=55,
            network_registry_mode="read_write",
            share_bans_to_network=True,
        )
    )
    db_session.add(
        Profile(
            telegram_user_id=5001,
            fingerprint_hash="0x" + "5" * 64,
            keystroke_profile={"rhythm": [1.0]},
            device_type="desktop",
        )
    )
    await db_session.commit()

    mock_chain = MagicMock()
    mock_chain.record_ban = AsyncMock(return_value="0xtx")

    with patch("singulr.services.bans._chain", mock_chain):
        await record_ban(
            db_session,
            telegram_user_id=5001,
            channel_id=55,
            category=BanCategory.SPAM,
            severity=BanSeverity.LOW,
        )

    mock_chain.record_ban.assert_awaited_once()


@pytest.mark.asyncio
async def test_share_bans_false_skips_chain_write(db_session: AsyncSession) -> None:
    """share_bans_to_network false keeps ban local only."""
    db_session.add(
        ChannelSecuritySettings(
            channel_id=56,
            network_registry_mode="read_write",
            share_bans_to_network=False,
        )
    )
    db_session.add(
        Profile(
            telegram_user_id=5002,
            fingerprint_hash="0x" + "6" * 64,
            keystroke_profile={"rhythm": [1.0]},
            device_type="desktop",
        )
    )
    await db_session.commit()

    mock_chain = MagicMock()
    mock_chain.record_ban = AsyncMock(return_value="0xtx")

    with patch("singulr.services.bans._chain", mock_chain):
        await record_ban(db_session, telegram_user_id=5002, channel_id=56)

    mock_chain.record_ban.assert_not_awaited()
