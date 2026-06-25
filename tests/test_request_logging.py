"""Request ID middleware tests."""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from httpx import ASGITransport
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from singulr.middleware.logging import RequestLoggingMiddleware


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


@pytest.mark.asyncio
async def test_log_json_emits_structured_access_log(caplog: pytest.LogCaptureFixture) -> None:
    """LOG_JSON mode writes one JSON object per request to singulr.access."""

    async def health(_request):
        return JSONResponse({"status": "ok"})

    app = Starlette(routes=[Route("/health", health)])
    app.add_middleware(RequestLoggingMiddleware, log_json=True)
    access_logger = logging.getLogger("singulr.access")
    access_logger.handlers.clear()
    access_logger.addHandler(caplog.handler)
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False
    caplog.set_level(logging.INFO, logger="singulr.access")

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    access_records = [record for record in caplog.records if record.name == "singulr.access"]
    assert access_records
    payload = json.loads(access_records[-1].message)
    assert payload["event"] == "http_request"
    assert payload["method"] == "GET"
    assert payload["path"] == "/health"
    assert payload["status"] == 200
