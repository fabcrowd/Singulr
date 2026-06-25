"""Health endpoint tests."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport


@pytest.mark.asyncio
async def test_health_reports_component_status() -> None:
    """GET /health returns db_ok, bot_configured, chain_enabled."""
    from singulr.main import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert "db_ok" in body
    assert "bot_configured" in body
    assert "chain_enabled" in body
    assert isinstance(body["db_ok"], bool)
    assert isinstance(body["bot_configured"], bool)
    assert isinstance(body["chain_enabled"], bool)
    assert body["version"] == "0.1.0"
    assert "uptime_seconds" in body
    assert isinstance(body["uptime_seconds"], (int, float))
    assert body["uptime_seconds"] >= 0
