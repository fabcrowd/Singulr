"""Token generation and validation."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.config import get_settings
from singulr.models import VerificationToken

MAX_TOKENS_PER_USER_PER_24H = 3


class TokenRateLimitError(Exception):
    """Raised when a user exceeds the per-day token generation limit."""


async def _count_recent_tokens(session: AsyncSession, telegram_user_id: int) -> int:
    """Count tokens issued to this user in the rolling 24-hour window."""
    window_start = datetime.now(UTC) - timedelta(hours=24)
    count = await session.scalar(
        select(func.count())
        .select_from(VerificationToken)
        .where(
            VerificationToken.telegram_user_id == telegram_user_id,
            VerificationToken.created_at >= window_start,
        )
    )
    return int(count or 0)


async def _invalidate_stale_tokens(session: AsyncSession, telegram_user_id: int) -> None:
    """Mark unused tokens for this user consumed so only the latest link works."""
    rows = (
        await session.scalars(
            select(VerificationToken).where(
                VerificationToken.telegram_user_id == telegram_user_id,
                VerificationToken.used.is_(False),
            )
        )
    ).all()
    for row in rows:
        row.used = True
    if rows:
        await session.commit()


async def create_token(
    session: AsyncSession,
    telegram_user_id: int,
    channel_id: int,
) -> str:
    """Create a single-use verification token."""
    if await _count_recent_tokens(session, telegram_user_id) >= MAX_TOKENS_PER_USER_PER_24H:
        raise TokenRateLimitError(
            f"User {telegram_user_id} exceeded {MAX_TOKENS_PER_USER_PER_24H} tokens per 24h"
        )

    await _invalidate_stale_tokens(session, telegram_user_id)

    settings = get_settings()
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(minutes=settings.token_expiry_minutes)
    row = VerificationToken(
        token=token,
        telegram_user_id=telegram_user_id,
        channel_id=channel_id,
        expires_at=expires,
        used=False,
    )
    session.add(row)
    await session.commit()
    return token


async def validate_token(session: AsyncSession, token: str) -> VerificationToken | None:
    """Return token row if valid and unused."""
    row = await session.scalar(select(VerificationToken).where(VerificationToken.token == token))
    if not row or row.used:
        return None
    if row.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        return None
    return row


async def mark_token_used(session: AsyncSession, token: str) -> None:
    """Mark token as consumed."""
    row = await session.scalar(select(VerificationToken).where(VerificationToken.token == token))
    if row:
        row.used = True
        await session.commit()
