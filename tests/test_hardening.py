"""Hardening tests for token claim and admin callbacks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.bot.handlers import on_callback
from singulr.services.tokens import claim_verification_token, create_token, validate_token


@pytest.mark.asyncio
async def test_claim_token_prevents_second_submit(db_session: AsyncSession) -> None:
    """Atomic claim allows only one consume per verification token."""
    token = await create_token(db_session, telegram_user_id=9100, channel_id=42)
    first = await claim_verification_token(db_session, token)
    assert first is not None
    second = await claim_verification_token(db_session, token)
    assert second is None
    assert await validate_token(db_session, token) is None


@pytest.mark.asyncio
async def test_permit_callback_rejects_non_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-admin cannot permit a pending user via callback."""
    query = MagicMock()
    query.data = "permit_42_701"
    query.answer = AsyncMock()
    query.from_user = MagicMock()
    query.from_user.id = 999
    query.get_bot = MagicMock()
    query.get_bot.return_value.get_chat_member = AsyncMock(
        return_value=MagicMock(status="member")
    )
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
    update = MagicMock()
    update.callback_query = query
    context = MagicMock()
    context.application = MagicMock()

    grant = AsyncMock()
    monkeypatch.setattr("singulr.bot.handlers.grant_access", grant)
    await on_callback(update, context)

    grant.assert_not_awaited()
    query.message.reply_text.assert_awaited_once()
    assert "administrator" in query.message.reply_text.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_approve_callback_rejects_non_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-admin cannot approve via legacy approve_ callback."""
    query = MagicMock()
    query.data = "approve_701"
    query.answer = AsyncMock()
    query.from_user = MagicMock()
    query.from_user.id = 999
    query.get_bot = MagicMock()
    query.get_bot.return_value.get_chat_member = AsyncMock(
        return_value=MagicMock(status="member")
    )
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
    update = MagicMock()
    update.callback_query = query
    context = MagicMock()
    context.application = MagicMock()

    grant = AsyncMock()
    monkeypatch.setattr("singulr.bot.handlers.grant_access", grant)
    await on_callback(update, context)

    grant.assert_not_awaited()
    query.message.reply_text.assert_awaited_once()
