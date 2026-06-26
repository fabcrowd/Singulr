"""Composite automation scoring for verify matching."""

from __future__ import annotations

from dataclasses import dataclass

from singulr.services.channel_policy import EffectivePolicy

WEBDRIVER_SCORE = 30
HEADLESS_UA_SCORE = 25
ZERO_PLUGINS_SCORE = 15
LOW_LANGUAGES_SCORE = 10
OUTER_DIMS_ZERO_SCORE = 20
SOFTWARE_RENDERER_SCORE = 15
SYNTHETIC_KEYSTROKE_SCORE = 20
TOO_FAST_VERIFY_SCORE = 15

_SOFTWARE_RENDERERS = ("swiftshader", "llvmpipe", "virtualbox")


@dataclass(frozen=True)
class AutomationOutcome:
    """Resolved automation policy action."""

    action: str
    reason: str


def compute_automation_score(env_flags: dict | None, factors: list[str]) -> int:
    """Sum weighted automation signals from env flags and keystroke risk labels."""
    score = 0
    if env_flags:
        if env_flags.get("webdriver"):
            score += WEBDRIVER_SCORE
        if env_flags.get("headless_ua"):
            score += HEADLESS_UA_SCORE
        plugins = env_flags.get("plugins_count")
        if plugins is not None and int(plugins) == 0:
            score += ZERO_PLUGINS_SCORE
        languages = env_flags.get("languages_count")
        if languages is not None and int(languages) <= 1:
            score += LOW_LANGUAGES_SCORE
        if env_flags.get("outer_dims_zero"):
            score += OUTER_DIMS_ZERO_SCORE
        renderer = str(env_flags.get("webgl_renderer") or "").lower()
        if renderer and any(token in renderer for token in _SOFTWARE_RENDERERS):
            score += SOFTWARE_RENDERER_SCORE
    if "synthetic_keystroke" in factors:
        score += SYNTHETIC_KEYSTROKE_SCORE
    if "too_fast_verify" in factors:
        score += TOO_FAST_VERIFY_SCORE
    return score


def resolve_automation_outcome(
    score: int,
    *,
    policy: EffectivePolicy,
) -> AutomationOutcome | None:
    """Map automation score and channel policy to pending/block, or defer to flag."""
    if score < policy.ai_pending_score_threshold:
        return None
    if policy.automation_flag_mode == "block":
        return AutomationOutcome("block", "Automation signals detected")
    if policy.automation_flag_mode == "pending":
        return AutomationOutcome("pending", "Automation review required")
    return None
