"""Tests for per-channel join velocity tracking."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Chat, ChatJoinRequest, User

from singulr.bot.handlers import on_join_request
from singulr.config import get_settings
from singulr.services.join_velocity import (
    JoinVelocityTracker,
    record_join_request,
    reset_join_velocity_tracker,
)


def test_join_velocity_below_burst_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Join count under threshold is not flagged as burst."""
    monkeypatch.setenv("JOIN_BURST_THRESHOLD", "5")
    get_settings.cache_clear()
    reset_join_velocity_tracker()

    for _ in range(4):
        snapshot = record_join_request(-100001)

    assert snapshot.join_count == 4
    assert snapshot.is_burst is False


def test_join_velocity_detects_burst(monkeypatch: pytest.MonkeyPatch) -> None:
    """Join count at threshold is flagged as burst."""
    monkeypatch.setenv("JOIN_BURST_THRESHOLD", "3")
    get_settings.cache_clear()
    reset_join_velocity_tracker()

    for _ in range(3):
        snapshot = record_join_request(-100002)

    assert snapshot.join_count == 3
    assert snapshot.is_burst is True


def test_join_velocity_tracker_prunes_old_events() -> None:
    """Events outside the window do not count toward burst detection."""
    tracker = JoinVelocityTracker(burst_threshold=2, window_seconds=60.0)
    tracker.record_join(-100003)
    bucket = tracker._events[-100003]
    bucket[0] = bucket[0] - 120.0

    snapshot = tracker.record_join(-100003)

    assert snapshot.join_count == 1
    assert snapshot.is_burst is False


@pytest.mark.asyncio
@patch("singulr.bot.handlers.send_verification_dm", new_callable=AsyncMock)
@patch("singulr.bot.handlers.restrict_member", new_callable=AsyncMock)
@patch("singulr.bot.handlers.get_channel_title", new_callable=AsyncMock, return_value="Burst Channel")
async def test_on_join_request_records_join_velocity(
    mock_title: AsyncMock,
    mock_restrict: AsyncMock,
    mock_dm: AsyncMock,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Join handler records each join request for velocity tracking."""
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8000")
    get_settings.cache_clear()
    reset_join_velocity_tracker()

    user = User(id=99001, is_bot=False, first_name="Joiner")
    chat = Chat(id=-100555, type=Chat.CHANNEL)
    request = ChatJoinRequest(
        chat=chat,
        from_user=user,
        date=MagicMock(),
        user_chat_id=99001,
    )
    update = MagicMock()
    update.chat_join_request = request
    context = MagicMock()
    context.application = MagicMock()

    with patch("singulr.bot.handlers.SessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "singulr.bot.handlers.record_join_request",
            wraps=record_join_request,
        ) as mock_record:
            await on_join_request(update, context)

    mock_record.assert_called_once_with(-100555)
