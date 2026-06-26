"""Tests for external HTTP social profile API provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from singulr.services.social_external import ExternalApiProvider
from singulr.services.social_profile import (
    SocialProfileContext,
    SocialProfileProviderError,
    get_composite_provider,
)
from singulr.services.channel_policy import EffectivePolicy


def _policy(**overrides: object) -> EffectivePolicy:
    base = {
        "channel_id": 42,
        "security_preset": "balanced",
        "ban_evasion_auto_deny_threshold": 0.92,
        "local_similarity_flag_threshold": 0.85,
        "network_registry_mode": "read",
        "share_bans_to_network": False,
        "network_auto_reject_categories": ["scam_fraud"],
        "instant_ban_categories": ["bot_abuse"],
        "social_profiling_enabled": True,
        "social_api_fail_mode": "fail_open",
        "social_pending_score_threshold": 40,
        "social_external_api_enabled": True,
        "admin_ops_chat_id": None,
    }
    base.update(overrides)
    return EffectivePolicy(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_external_api_provider_maps_json_response() -> None:
    """HTTP 200 JSON maps to SocialProfileResult fields."""
    provider = ExternalApiProvider(url="https://social.example/score", api_key="secret")

    mock_response = httpx.Response(
        200,
        json={
            "risk_score": 70,
            "hard_categories": ["bot_abuse"],
            "soft_signals": ["vendor_flag"],
            "summary": "API: bot signals",
        },
        request=httpx.Request("POST", "https://social.example/score"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await provider.analyze(
            SocialProfileContext(
                telegram_user_id=500,
                channel_id=42,
                username="testuser",
                display_name="Test",
            )
        )

    assert "bot_abuse" in result.hard_categories
    assert result.risk_score == 70
    assert "external_api" in result.sources


@pytest.mark.asyncio
async def test_external_api_provider_raises_on_http_error() -> None:
    """Network failures raise SocialProfileProviderError."""
    provider = ExternalApiProvider(url="https://social.example/score")

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("timeout"),
    ):
        with pytest.raises(SocialProfileProviderError):
            await provider.analyze(
                SocialProfileContext(telegram_user_id=501, channel_id=42)
            )


def test_composite_includes_external_when_policy_and_url_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """External provider is wired when channel opts in and URL is configured."""
    monkeypatch.setenv("SOCIAL_API_URL", "https://social.example/score")
    from singulr.config import get_settings

    get_settings.cache_clear()
    providers = get_composite_provider(_policy(social_external_api_enabled=True))
    names = [type(p).__name__ for p in providers._providers]
    assert "ExternalApiProvider" in names


@pytest.mark.asyncio
async def test_external_api_provider_raises_on_malformed_json() -> None:
    """Non-JSON API body raises SocialProfileProviderError."""
    provider = ExternalApiProvider(url="https://social.example/score")
    mock_response = httpx.Response(
        200,
        text="not-json",
        request=httpx.Request("POST", "https://social.example/score"),
    )
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        with pytest.raises(SocialProfileProviderError):
            await provider.analyze(
                SocialProfileContext(telegram_user_id=502, channel_id=42)
            )


@pytest.mark.asyncio
async def test_external_api_provider_does_not_log_api_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Logs must never contain the configured API key."""
    secret = "super-secret-social-key"
    provider = ExternalApiProvider(url="https://social.example/score", api_key=secret)
    mock_response = httpx.Response(
        200,
        json={"risk_score": 0, "hard_categories": [], "soft_signals": [], "summary": "ok"},
        request=httpx.Request("POST", "https://social.example/score"),
    )
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        with caplog.at_level("DEBUG"):
            await provider.analyze(
                SocialProfileContext(telegram_user_id=503, channel_id=42)
            )
    combined = caplog.text + str(mock_response.request.headers)
    assert secret not in combined
    assert "Bearer" not in caplog.text


def test_composite_omits_external_when_channel_opt_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """External provider skipped when channel has not opted in."""
    monkeypatch.setenv("SOCIAL_API_URL", "https://social.example/score")
    from singulr.config import get_settings

    get_settings.cache_clear()
    providers = get_composite_provider(_policy(social_external_api_enabled=False))
    names = [type(p).__name__ for p in providers._providers]
    assert "ExternalApiProvider" not in names
