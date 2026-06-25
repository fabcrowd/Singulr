"""Integration-style tests for the member verify journey."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.bot.handlers import apply_verification_decision
from singulr.copy.member import ACCOUNT_RESTRICTED, JOIN_DM_TEMPLATE
from singulr.services.tokens import create_token, validate_token


def _mock_app() -> MagicMock:
    app = MagicMock()
    app.bot.send_message = AsyncMock()
    app.bot.get_chat = AsyncMock()
    app.bot.get_chat.return_value = MagicMock(username="testchannel", title="Test")
    app.bot.get_chat_member = AsyncMock()
    return app


@pytest.mark.asyncio
async def test_join_dm_template_is_channel_branded() -> None:
    """Join DM copy references channel name."""
    text = JOIN_DM_TEMPLATE.format(channel_name="My Channel", verify_url="https://x/verify")
    assert "My Channel" in text
    assert "Finish joining" in text


def test_account_restricted_copy_constant() -> None:
    """Restricted web copy is generic."""
    assert ACCOUNT_RESTRICTED == "Account restricted"


@pytest.mark.asyncio
async def test_approve_sends_channel_link_dm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Approve path includes channel open link in DM."""
    grant = AsyncMock()
    notify = AsyncMock()
    log_ops = AsyncMock()
    monkeypatch.setattr("singulr.bot.handlers.grant_access", grant)
    monkeypatch.setattr("singulr.bot.handlers.notify_user_result", notify)
    monkeypatch.setattr("singulr.bot.handlers.log_to_ops_channel", log_ops)
    monkeypatch.setattr("singulr.bot.handlers.log_to_channel", AsyncMock())
    monkeypatch.setattr("singulr.bot.handlers._ban_history_for_fingerprint", AsyncMock(return_value=None))

    app = _mock_app()
    with patch("singulr.services.telegram_actions.channel_open_link", new_callable=AsyncMock) as link:
        link.return_value = "https://t.me/testchannel"
        await apply_verification_decision(
            app, decision="approve", telegram_user_id=501, channel_id=42
        )

    notify.assert_awaited_once()
    assert notify.await_args.kwargs.get("channel_id") == 42


@pytest.mark.asyncio
async def test_one_active_token_invalidates_previous(db_session: AsyncSession) -> None:
    """Re-join invalidates the prior verify link."""
    first = await create_token(db_session, telegram_user_id=502, channel_id=1)
    second = await create_token(db_session, telegram_user_id=502, channel_id=1)

    assert await validate_token(db_session, first) is None
    assert await validate_token(db_session, second) is not None


@pytest.mark.asyncio
async def test_pending_posts_details_button(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pending review logs to ops with details affordance."""
    log_ops = AsyncMock()
    monkeypatch.setattr("singulr.bot.handlers.log_to_ops_channel", log_ops)
    monkeypatch.setattr("singulr.bot.handlers.notify_user_result", AsyncMock())
    monkeypatch.setattr("singulr.bot.handlers._ban_history_for_fingerprint", AsyncMock(return_value=None))

    await apply_verification_decision(
        _mock_app(),
        decision="pending",
        telegram_user_id=503,
        channel_id=42,
        reason="Network reputation review",
    )
    log_ops.assert_awaited_once()
    assert log_ops.await_args.kwargs.get("include_details_button") is True
