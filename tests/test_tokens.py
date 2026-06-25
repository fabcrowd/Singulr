"""Tests for verification token lifecycle and rate limits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.services.tokens import (
    MAX_TOKENS_PER_USER_PER_24H,
    TokenRateLimitError,
    create_token,
    mark_token_used,
    validate_token,
)


@pytest.mark.asyncio
async def test_create_token_returns_usable_token(db_session: AsyncSession) -> None:
    """Fresh token validates and maps to the issuing user/channel."""
    token = await create_token(db_session, telegram_user_id=42, channel_id=99)

    assert token
    row = await validate_token(db_session, token)
    assert row is not None
    assert row.telegram_user_id == 42
    assert row.channel_id == 99
    assert row.used is False


@pytest.mark.asyncio
async def test_validate_token_rejects_expired(db_session: AsyncSession) -> None:
    """Expired tokens are not accepted."""
    token = await create_token(db_session, telegram_user_id=1, channel_id=2)
    row = await validate_token(db_session, token)
    assert row is not None

    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    assert await validate_token(db_session, token) is None


@pytest.mark.asyncio
async def test_validate_token_rejects_used(db_session: AsyncSession) -> None:
    """Already-used tokens are not accepted."""
    token = await create_token(db_session, telegram_user_id=1, channel_id=2)
    row = await validate_token(db_session, token)
    assert row is not None

    row.used = True
    await db_session.commit()

    assert await validate_token(db_session, token) is None


@pytest.mark.asyncio
async def test_mark_token_used_prevents_reuse(db_session: AsyncSession) -> None:
    """Consuming a token blocks subsequent validation."""
    token = await create_token(db_session, telegram_user_id=5, channel_id=6)
    assert await validate_token(db_session, token) is not None

    await mark_token_used(db_session, token)

    assert await validate_token(db_session, token) is None


@pytest.mark.asyncio
async def test_create_token_rate_limit_blocks_fourth_within_24h(db_session: AsyncSession) -> None:
    """Fourth token within 24h raises TokenRateLimitError."""
    user_id = 42_001
    channel_id = -100_123

    for _ in range(MAX_TOKENS_PER_USER_PER_24H):
        token = await create_token(db_session, user_id, channel_id)
        assert token

    with pytest.raises(TokenRateLimitError):
        await create_token(db_session, user_id, channel_id)
