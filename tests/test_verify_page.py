"""Smoke tests for the public verification page."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport


@pytest.mark.asyncio
async def test_verify_page_returns_html() -> None:
    """GET /verify serves verify.html."""
    from singulr.main import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/verify")

    assert response.status_code == 200
    assert "verify.js" in response.text


@pytest.mark.asyncio
async def test_verify_static_css() -> None:
    """Static verify.css is served."""
    from singulr.main import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/static/verify.css")

    assert response.status_code == 200
    assert "text/css" in response.headers.get("content-type", "")
