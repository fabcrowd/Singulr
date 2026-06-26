"""Rate limit tests for verify endpoints."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.services.rate_limit import reset_verify_limiter
from singulr.services.tokens import create_token
from verify_helpers import challenge_proof_for


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
        mock_settings.return_value.verify_precheck_per_token_per_minute = 100
        first = await api_client.post("/api/verify/precheck", json=body)
        second = await api_client.post("/api/verify/precheck", json=body)
        third = await api_client.post("/api/verify/precheck", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["detail"] == "rate_limited"


@pytest.mark.asyncio
async def test_submit_returns_429_when_rate_limited(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Excess submit requests from one IP return HTTP 429."""
    from singulr.config import VERIFICATION_SENTENCE

    token = await create_token(db_session, telegram_user_id=8802, channel_id=1)
    proof = await challenge_proof_for(api_client, token, visitor_id="rate-limit-submit")
    body = {
        "token": token,
        "visitor_id": "rate-limit-submit",
        "device_type": "desktop",
        "typed_text": VERIFICATION_SENTENCE,
        "keystrokes": [{"key": "W", "down": 0, "up": 80, "flight": 0}],
        "privacy_accepted": True,
        "challenge_proof": proof,
    }

    with patch("singulr.api.verify.get_settings") as mock_settings:
        mock_settings.return_value.verify_rate_limit_per_minute = 1
        mock_settings.return_value.verify_precheck_per_token_per_minute = 100
        first = await api_client.post("/api/verify/submit", json=body)
        second = await api_client.post("/api/verify/submit", json=body)

    assert first.status_code in {200, 400, 410}
    assert second.status_code == 429
    assert second.json()["detail"] == "rate_limited"


@pytest.mark.asyncio
async def test_precheck_returns_429_when_per_token_rate_limited(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Excess precheck requests for one token return HTTP 429."""
    token = await create_token(db_session, telegram_user_id=8803, channel_id=1)
    body = {"token": token, "visitor_id": "token-rate-visitor"}

    with patch("singulr.api.verify.get_settings") as mock_settings:
        mock_settings.return_value.verify_rate_limit_per_minute = 100
        mock_settings.return_value.verify_precheck_per_token_per_minute = 2
        first = await api_client.post("/api/verify/precheck", json=body)
        second = await api_client.post("/api/verify/precheck", json=body)
        third = await api_client.post("/api/verify/precheck", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["detail"] == "rate_limited"
