"""Rate limit tests for verify endpoints."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.services.rate_limit import reset_verify_limiter
from singulr.services.tokens import create_token


@pytest.fixture(autouse=True)
def _clear_rate_limiter() -> None:
    """Isolate rate limiter state between tests."""
    reset_verify_limiter()
    yield
    reset_verify_limiter()


@pytest.mark.asyncio
async def test_precheck_returns_429_when_rate_limited(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Excess precheck requests from one IP return HTTP 429."""
    token = await create_token(db_session, telegram_user_id=8801, channel_id=1)
    body = {"token": token, "visitor_id": "rate-limit-visitor"}

    with patch("singulr.api.verify.get_settings") as mock_settings:
        mock_settings.return_value.verify_rate_limit_per_minute = 2
        first = await api_client.post("/api/verify/precheck", json=body)
        second = await api_client.post("/api/verify/precheck", json=body)
        third = await api_client.post("/api/verify/precheck", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["detail"] == "rate_limited"
