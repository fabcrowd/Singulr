"""Tests for authenticated internal ban API."""

from __future__ import annotations

import httpx
import pytest

from singulr.models import Ban


@pytest.mark.asyncio
async def test_internal_ban_requires_admin_key(api_client: httpx.AsyncClient) -> None:
    """POST /api/internal/ban without X-Admin-Key returns 401."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ADMIN_API_KEY", "secret-internal-key")
        from singulr.config import get_settings

        get_settings.cache_clear()
        response = await api_client.post(
            "/api/internal/ban",
            json={"telegram_user_id": 999001, "channel_id": 1, "reason": "test"},
        )
        get_settings.cache_clear()

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_internal_ban_persists_with_valid_key(
    api_client: httpx.AsyncClient,
    db_session,
) -> None:
    """POST /api/internal/ban with valid key records ban."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ADMIN_API_KEY", "secret-internal-key")
        from singulr.config import get_settings
        from sqlalchemy import select

        get_settings.cache_clear()
        response = await api_client.post(
            "/api/internal/ban",
            json={"telegram_user_id": 999002, "channel_id": 42, "reason": "audit_test"},
            headers={"X-Admin-Key": "secret-internal-key"},
        )
        get_settings.cache_clear()

    assert response.status_code == 200
    body = response.json()
    assert body.get("ok") is True
    assert body.get("fingerprint_hash")

    row = await db_session.scalar(select(Ban).where(Ban.telegram_user_id == 999002))
    assert row is not None
    assert row.reason == "audit_test"
