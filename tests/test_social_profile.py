"""Tests for social profile provider."""

from __future__ import annotations

import pytest

from singulr.services.social_profile import MockSocialProfileProvider


@pytest.mark.asyncio
async def test_mock_provider_hard_bot_category(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured user id returns hard bot_abuse category."""
    monkeypatch.setenv("SOCIAL_PROFILE_PROVIDER", "mock")
    monkeypatch.setenv("MOCK_SOCIAL_HARD_USER_IDS", "90001")
    from singulr.config import get_settings

    get_settings.cache_clear()
    provider = MockSocialProfileProvider()
    result = await provider.analyze(telegram_user_id=90001)
    assert "bot_abuse" in result.hard_categories


@pytest.mark.asyncio
async def test_mock_provider_soft_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured user id returns soft social signals."""
    monkeypatch.setenv("MOCK_SOCIAL_SOFT_USER_IDS", "90002")
    from singulr.config import get_settings

    get_settings.cache_clear()
    provider = MockSocialProfileProvider()
    result = await provider.analyze(telegram_user_id=90002)
    assert result.soft_signals
    assert result.risk_score >= 40
