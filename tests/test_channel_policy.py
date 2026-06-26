"""Tests for per-channel security policy loading."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.models import ChannelSecuritySettings
from singulr.services.channel_policy import EffectivePolicy, get_effective_channel_policy


@pytest.mark.asyncio
async def test_missing_row_uses_balanced_config_defaults(db_session: AsyncSession) -> None:
    """Channels without persisted settings inherit env/config defaults."""
    policy = await get_effective_channel_policy(db_session, channel_id=99001)

    assert isinstance(policy, EffectivePolicy)
    assert policy.channel_id == 99001
    assert policy.security_preset == "balanced"
    assert policy.ban_evasion_auto_deny_threshold == 0.92
    assert policy.local_similarity_flag_threshold == 0.85
    assert policy.network_registry_mode == "read"
    assert policy.instant_ban_categories == ["impersonation", "bot_abuse"]
    assert policy.social_profiling_enabled is True
    assert policy.social_api_fail_mode == "fail_open"
    assert policy.automation_flag_mode == "flag"
    assert policy.ai_pending_score_threshold == 50
    assert policy.admin_ops_chat_id is None


@pytest.mark.asyncio
async def test_persisted_row_overrides_config_defaults(db_session: AsyncSession) -> None:
    """Stored ChannelSecuritySettings override global defaults for that channel."""
    channel_id = 99002
    db_session.add(
        ChannelSecuritySettings(
            channel_id=channel_id,
            security_preset="strict",
            ban_evasion_auto_deny_threshold=0.88,
            local_similarity_flag_threshold=0.75,
            network_registry_mode="read_write",
            admin_ops_chat_id=-1001234567890,
        )
    )
    await db_session.commit()

    policy = await get_effective_channel_policy(db_session, channel_id=channel_id)

    assert policy.security_preset == "strict"
    assert policy.ban_evasion_auto_deny_threshold == 0.88
    assert policy.local_similarity_flag_threshold == 0.75
    assert policy.network_registry_mode == "read_write"
    assert policy.admin_ops_chat_id == -1001234567890


@pytest.mark.asyncio
async def test_persisted_automation_fields_override_defaults(db_session: AsyncSession) -> None:
    """Stored automation policy fields override global defaults."""
    channel_id = 99003
    db_session.add(
        ChannelSecuritySettings(
            channel_id=channel_id,
            security_preset="strict",
            automation_flag_mode="pending",
            ai_pending_score_threshold=35,
        )
    )
    await db_session.commit()

    policy = await get_effective_channel_policy(db_session, channel_id=channel_id)

    assert policy.automation_flag_mode == "pending"
    assert policy.ai_pending_score_threshold == 35


def test_effective_policy_field_types() -> None:
    """EffectivePolicy exposes typed threshold and mode fields for matching."""
    policy = EffectivePolicy(
        channel_id=1,
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

    assert isinstance(policy.ban_evasion_auto_deny_threshold, float)
    assert isinstance(policy.local_similarity_flag_threshold, float)
    assert isinstance(policy.network_registry_mode, str)
    assert isinstance(policy.security_preset, str)
    assert isinstance(policy.automation_flag_mode, str)
    assert isinstance(policy.ai_pending_score_threshold, int)
