"""Per-channel security policy resolution with config fallbacks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

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
    share_bans_to_network: bool
    network_auto_reject_categories: list[str]
    instant_ban_categories: list[str]
    social_profiling_enabled: bool
    social_api_fail_mode: str
    social_pending_score_threshold: int
    social_external_api_enabled: bool
    admin_ops_chat_id: int | None
    automation_flag_mode: str
    ai_pending_score_threshold: int


DEFAULT_NETWORK_AUTO_REJECT = ["scam_fraud", "raid_coordination"]
DEFAULT_INSTANT_BAN_CATEGORIES = ["impersonation", "bot_abuse"]


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
            share_bans_to_network=False,
            network_auto_reject_categories=list(DEFAULT_NETWORK_AUTO_REJECT),
            instant_ban_categories=list(DEFAULT_INSTANT_BAN_CATEGORIES),
            social_profiling_enabled=settings.default_social_profiling_enabled,
            social_api_fail_mode=settings.default_social_api_fail_mode,
            social_pending_score_threshold=settings.default_social_pending_score_threshold,
            social_external_api_enabled=False,
            admin_ops_chat_id=settings.log_channel_id or None,
            automation_flag_mode=settings.default_automation_flag_mode,
            ai_pending_score_threshold=settings.default_ai_pending_score_threshold,
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
        share_bans_to_network=row.share_bans_to_network,
        network_auto_reject_categories=list(
            row.network_auto_reject_categories or DEFAULT_NETWORK_AUTO_REJECT
        ),
        instant_ban_categories=list(
            row.instant_ban_categories or DEFAULT_INSTANT_BAN_CATEGORIES
        ),
        social_profiling_enabled=(
            row.social_profiling_enabled
            if row.social_profiling_enabled is not None
            else settings.default_social_profiling_enabled
        ),
        social_api_fail_mode=row.social_api_fail_mode or settings.default_social_api_fail_mode,
        social_pending_score_threshold=(
            row.social_pending_score_threshold
            if row.social_pending_score_threshold is not None
            else settings.default_social_pending_score_threshold
        ),
        social_external_api_enabled=bool(row.social_external_api_enabled),
        admin_ops_chat_id=row.admin_ops_chat_id,
        automation_flag_mode=(
            row.automation_flag_mode
            if row.automation_flag_mode is not None
            else settings.default_automation_flag_mode
        ),
        ai_pending_score_threshold=(
            row.ai_pending_score_threshold
            if row.ai_pending_score_threshold is not None
            else settings.default_ai_pending_score_threshold
        ),
    )


@dataclass(frozen=True)
class PresetBundle:
    """Threshold bundle for a security preset."""

    security_preset: str
    ban_evasion_auto_deny_threshold: float
    local_similarity_flag_threshold: float
    network_registry_mode: str


PRESET_BUNDLES: dict[str, PresetBundle] = {
    "open": PresetBundle("open", 0.95, 0.90, "off"),
    "balanced": PresetBundle("balanced", 0.92, 0.85, "read"),
    "strict": PresetBundle("strict", 0.88, 0.78, "read"),
}

# Evasion strictness tweaks applied on top of the chosen preset.
EVASION_ADJUSTMENTS: dict[str, tuple[float, float]] = {
    "high_only": (0.0, 0.0),
    "flag_medium": (-0.02, -0.03),
    "review_most": (-0.04, -0.08),
}


def resolve_wizard_thresholds(preset: str, evasion_mode: str) -> PresetBundle:
    """Combine preset bundle with ban-evasion strictness selection."""
    bundle = PRESET_BUNDLES.get(preset, PRESET_BUNDLES["balanced"])
    auto_delta, flag_delta = EVASION_ADJUSTMENTS.get(evasion_mode, (0.0, 0.0))
    return PresetBundle(
        security_preset=bundle.security_preset,
        ban_evasion_auto_deny_threshold=max(0.5, bundle.ban_evasion_auto_deny_threshold + auto_delta),
        local_similarity_flag_threshold=max(0.5, bundle.local_similarity_flag_threshold + flag_delta),
        network_registry_mode=bundle.network_registry_mode,
    )


async def upsert_channel_security_settings(
    session: AsyncSession,
    *,
    channel_id: int,
    preset: str,
    evasion_mode: str,
    admin_ops_chat_id: int | None,
    network_registry_mode: str | None = None,
    network_auto_reject_categories: list[str] | None = None,
    instant_ban_categories: list[str] | None = None,
    social_profiling_enabled: bool | None = None,
    social_external_api_enabled: bool | None = None,
) -> ChannelSecuritySettings:
    """Create or update channel policy from wizard answers."""
    resolved = resolve_wizard_thresholds(preset, evasion_mode)
    row = await session.get(ChannelSecuritySettings, channel_id)
    if row is None:
        row = ChannelSecuritySettings(channel_id=channel_id)
        session.add(row)
    row.security_preset = resolved.security_preset
    row.ban_evasion_auto_deny_threshold = resolved.ban_evasion_auto_deny_threshold
    row.local_similarity_flag_threshold = resolved.local_similarity_flag_threshold
    mode = network_registry_mode if network_registry_mode is not None else resolved.network_registry_mode
    row.network_registry_mode = mode
    row.share_bans_to_network = mode == "read_write"
    if network_auto_reject_categories is not None:
        row.network_auto_reject_categories = network_auto_reject_categories
    elif row.network_auto_reject_categories is None:
        row.network_auto_reject_categories = list(DEFAULT_NETWORK_AUTO_REJECT)
    if row.instant_ban_categories is None:
        row.instant_ban_categories = list(DEFAULT_INSTANT_BAN_CATEGORIES)
    if instant_ban_categories is not None:
        row.instant_ban_categories = list(instant_ban_categories)
    if social_profiling_enabled is not None:
        row.social_profiling_enabled = social_profiling_enabled
    if social_external_api_enabled is not None:
        row.social_external_api_enabled = social_external_api_enabled
    if row.social_profiling_enabled is None:
        row.social_profiling_enabled = True
    if row.social_api_fail_mode is None:
        row.social_api_fail_mode = "fail_open"
    if row.social_pending_score_threshold is None:
        row.social_pending_score_threshold = get_settings().default_social_pending_score_threshold
    if row.social_external_api_enabled is None:
        row.social_external_api_enabled = False
    row.admin_ops_chat_id = admin_ops_chat_id
    row.wizard_completed_at = datetime.now(UTC)
    row.wizard_version = 3
    await session.commit()
    await session.refresh(row)
    return row


def format_policy_summary(row: ChannelSecuritySettings) -> str:
    """Human-readable summary for wizard confirmation."""
    ops = row.admin_ops_chat_id if row.admin_ops_chat_id else "(not set)"
    categories = ", ".join(row.network_auto_reject_categories or DEFAULT_NETWORK_AUTO_REJECT)
    instant = ", ".join(row.instant_ban_categories or DEFAULT_INSTANT_BAN_CATEGORIES)
    share = "yes" if row.share_bans_to_network else "no"
    social = "on" if row.social_profiling_enabled else "off"
    external = "on" if row.social_external_api_enabled else "off"
    return (
        f"Preset: {row.security_preset}\n"
        f"Auto-deny threshold: {row.ban_evasion_auto_deny_threshold:.2f}\n"
        f"Flag threshold: {row.local_similarity_flag_threshold:.2f}\n"
        f"Network registry: {row.network_registry_mode}\n"
        f"Share bans to network: {share}\n"
        f"Network auto-reject: {categories}\n"
        f"Instant-ban categories: {instant}\n"
        f"Social profiling: {social} (external API: {external}, fail mode: {row.social_api_fail_mode})\n"
        f"Ops chat: {ops}"
    )
