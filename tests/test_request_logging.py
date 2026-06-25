"""Request ID middleware tests."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport


@pytest.mark.asyncio
async def test_health_includes_x_request_id_header() -> None:
    """Responses include X-Request-ID from middleware."""
    from singulr.main import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    request_id = response.headers.get("x-request-id")
    assert request_id
    assert len(request_id) >= 8


@pytest.mark.asyncio
async def test_client_request_id_is_echoed() -> None:
    """Middleware preserves an incoming X-Request-ID."""
    from singulr.main import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": "client-req-abc"})

    assert response.headers.get("x-request-id") == "client-req-abc"
