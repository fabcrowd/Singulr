"""Tests for social profile providers, cache, and policy integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.models import VerificationToken
from singulr.services.channel_policy import EffectivePolicy
from singulr.services.matching import Decision, check_known_bad
from singulr.services.social_profile import (
    MockSocialProfileProvider,
    SocialProfileContext,
    SocialProfileProviderError,
    SocialProfileResult,
    TelegramNativeProvider,
    analyze_social_profile,
    get_cached_social_profile,
    merge_social_results,
    result_from_cache_dict,
    result_to_cache_dict,
)
from singulr.services.tokens import create_token


def _policy(**overrides: object) -> EffectivePolicy:
    base = {
        "channel_id": 42,
        "security_preset": "balanced",
        "ban_evasion_auto_deny_threshold": 0.92,
        "local_similarity_flag_threshold": 0.85,
        "network_registry_mode": "read",
        "share_bans_to_network": False,
        "network_auto_reject_categories": ["scam_fraud", "raid_coordination"],
        "instant_ban_categories": ["impersonation", "bot_abuse"],
        "social_profiling_enabled": True,
        "social_api_fail_mode": "fail_open",
        "social_pending_score_threshold": 40,
        "admin_ops_chat_id": None,
    }
    base.update(overrides)
    return EffectivePolicy(**base)  # type: ignore[arg-type]


def _chain_mock() -> MagicMock:
    chain = MagicMock()
    chain.is_banned = AsyncMock(return_value=False)
    chain.get_reputation = AsyncMock(return_value={"score": 0, "active_bans": 0})
    return chain


@pytest.mark.asyncio
async def test_telegram_native_brand_overlap_is_soft_pending_signal() -> None:
    """Display name overlapping channel title yields soft signals only."""
    provider = TelegramNativeProvider()
    result = await provider.analyze(
        SocialProfileContext(
            telegram_user_id=1,
            channel_id=42,
            display_name="Singulr Official Support",
            channel_title="Singulr Community",
        )
    )
    assert "display_name_brand_overlap" in result.soft_signals
    assert not result.hard_categories
    assert result.risk_score >= 40
    assert "telegram_native" in result.sources


@pytest.mark.asyncio
async def test_telegram_native_no_username_soft_signal() -> None:
    """Missing username adds a soft signal."""
    provider = TelegramNativeProvider()
    result = await provider.analyze(
        SocialProfileContext(telegram_user_id=2, channel_id=42, display_name="Alice")
    )
    assert "no_username" in result.soft_signals


@pytest.mark.asyncio
async def test_mock_provider_hard_bot_category(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured user id returns hard bot_abuse category."""
    monkeypatch.setenv("MOCK_SOCIAL_HARD_USER_IDS", "90001")
    from singulr.config import get_settings

    get_settings.cache_clear()
    provider = MockSocialProfileProvider()
    result = await provider.analyze(
        SocialProfileContext(telegram_user_id=90001, channel_id=42)
    )
    assert "bot_abuse" in result.hard_categories


@pytest.mark.asyncio
async def test_mock_provider_soft_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured user id returns soft social signals."""
    monkeypatch.setenv("MOCK_SOCIAL_SOFT_USER_IDS", "90002")
    from singulr.config import get_settings

    get_settings.cache_clear()
    provider = MockSocialProfileProvider()
    result = await provider.analyze(
        SocialProfileContext(telegram_user_id=90002, channel_id=42)
    )
    assert result.soft_signals
    assert result.risk_score >= 40


def test_merge_social_results_unions_categories_and_max_score() -> None:
    """Composite merge keeps max score and unions lists."""
    merged = merge_social_results(
        SocialProfileResult(risk_score=30, soft_signals=["a"], sources=["one"]),
        SocialProfileResult(
            risk_score=55,
            hard_categories=["bot_abuse"],
            soft_signals=["b"],
            summary="second",
            sources=["two"],
        ),
    )
    assert merged.risk_score == 55
    assert merged.hard_categories == ["bot_abuse"]
    assert merged.soft_signals == ["a", "b"]
    assert merged.sources == ["one", "two"]


def test_result_cache_roundtrip() -> None:
    """Cache dict serialization round-trips cleanly."""
    original = SocialProfileResult(
        risk_score=50,
        hard_categories=["bot_abuse"],
        soft_signals=["no_username"],
        summary="test",
        sources=["telegram_native"],
    )
    restored = result_from_cache_dict(result_to_cache_dict(original))
    assert restored.risk_score == original.risk_score
    assert restored.hard_categories == original.hard_categories
    assert restored.soft_signals == original.soft_signals


@pytest.mark.asyncio
async def test_analyze_social_profile_caches_on_token_row(db_session: AsyncSession) -> None:
    """First analysis persists cache on the verification token."""
    token = await create_token(
        db_session,
        telegram_user_id=8001,
        channel_id=42,
        join_display_name="Singulr Official",
        join_channel_title="Singulr Community",
    )
    row = await db_session.scalar(
        select(VerificationToken).where(VerificationToken.token == token)
    )
    assert row is not None
    ctx = SocialProfileContext(
        telegram_user_id=8001,
        channel_id=42,
        display_name=row.join_display_name,
        channel_title=row.join_channel_title,
        verify_token=token,
    )
    first = await analyze_social_profile(
        db_session,
        ctx,
        policy=_policy(),
        token_row=row,
    )
    await db_session.commit()
    assert first.soft_signals

    cached = await get_cached_social_profile(
        db_session,
        telegram_user_id=8001,
        channel_id=42,
        verify_token=token,
    )
    assert cached is not None
    assert cached.soft_signals == first.soft_signals

    with patch(
        "singulr.services.social_profile.get_composite_provider",
    ) as mock_factory:
        mock_factory.return_value.analyze = AsyncMock(
            side_effect=AssertionError("should use cache")
        )
        second = await analyze_social_profile(
            db_session,
            ctx,
            policy=_policy(),
            token_row=row,
            refresh=False,
        )
    assert second.soft_signals == first.soft_signals


@pytest.mark.asyncio
async def test_matching_pending_on_brand_overlap_heuristic(db_session: AsyncSession) -> None:
    """Verify submit matching sends brand-overlap profiles to pending review."""
    token = await create_token(
        db_session,
        telegram_user_id=8002,
        channel_id=42,
        join_display_name="Singulr Official Support",
        join_channel_title="Singulr Community",
    )
    row = await db_session.scalar(
        select(VerificationToken).where(VerificationToken.token == token)
    )
    assert row is not None

    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=8002,
        fingerprint_hash="0x" + "55" * 32,
        ip_hash=None,
        channel_id=42,
        policy=_policy(),
        token_row=row,
    )
    assert result.decision == Decision.PENDING
    assert any("social_soft" in factor for factor in result.risk_factors)


@pytest.mark.asyncio
async def test_fail_closed_forces_pending_on_provider_error(db_session: AsyncSession) -> None:
    """fail_closed policy pending when all providers fail."""
    token = await create_token(db_session, telegram_user_id=8003, channel_id=42)
    row = await db_session.scalar(
        select(VerificationToken).where(VerificationToken.token == token)
    )
    assert row is not None

    with patch(
        "singulr.services.social_profile.get_composite_provider",
    ) as mock_factory:
        mock_factory.return_value.analyze = AsyncMock(
            side_effect=SocialProfileProviderError("down")
        )
        result = await check_known_bad(
            db_session,
            _chain_mock(),
            telegram_user_id=8003,
            fingerprint_hash="0x" + "66" * 32,
            ip_hash=None,
            channel_id=42,
            policy=_policy(social_api_fail_mode="fail_closed"),
            token_row=row,
        )
    assert result.decision == Decision.PENDING
    assert "social_provider_error" in result.risk_factors


@pytest.mark.asyncio
async def test_social_profiling_disabled_skips_signals(db_session: AsyncSession) -> None:
    """Disabled social profiling returns clean approve path."""
    token = await create_token(
        db_session,
        telegram_user_id=8004,
        channel_id=42,
        join_display_name="Singulr Official Support",
        join_channel_title="Singulr Community",
    )
    row = await db_session.scalar(
        select(VerificationToken).where(VerificationToken.token == token)
    )
    assert row is not None

    result = await check_known_bad(
        db_session,
        _chain_mock(),
        telegram_user_id=8004,
        fingerprint_hash="0x" + "77" * 32,
        ip_hash=None,
        channel_id=42,
        policy=_policy(social_profiling_enabled=False),
        token_row=row,
    )
    assert result.decision == Decision.APPROVE
