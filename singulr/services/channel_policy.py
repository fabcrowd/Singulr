"""Per-channel security policy resolution with config fallbacks."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from singulr.config import get_settings
from singulr.models import ChannelSecuritySettings


@dataclass(frozen=True)
class EffectivePolicy:
    """Resolved security knobs for a channel join or verify decision."""

    channel_id: int
    security_preset: str
    ban_evasion_auto_deny_threshold: float
    local_similarity_flag_threshold: float
    network_registry_mode: str
    admin_ops_chat_id: int | None


async def get_effective_channel_policy(
    session: AsyncSession,
    channel_id: int,
) -> EffectivePolicy:
    """Load channel policy from DB, falling back to config defaults when unset."""
    settings = get_settings()
    row = await session.get(ChannelSecuritySettings, channel_id)

    if row is None:
        return EffectivePolicy(
            channel_id=channel_id,
            security_preset=settings.default_security_preset,
            ban_evasion_auto_deny_threshold=settings.ban_evasion_auto_deny_threshold,
            local_similarity_flag_threshold=settings.local_similarity_flag_threshold,
            network_registry_mode=settings.default_network_registry_mode,
            admin_ops_chat_id=settings.log_channel_id or None,
        )

    return EffectivePolicy(
        channel_id=channel_id,
        security_preset=row.security_preset,
        ban_evasion_auto_deny_threshold=(
            row.ban_evasion_auto_deny_threshold
            if row.ban_evasion_auto_deny_threshold is not None
            else settings.ban_evasion_auto_deny_threshold
        ),
        local_similarity_flag_threshold=(
            row.local_similarity_flag_threshold
            if row.local_similarity_flag_threshold is not None
            else settings.local_similarity_flag_threshold
        ),
        network_registry_mode=row.network_registry_mode,
        admin_ops_chat_id=row.admin_ops_chat_id,
    )
