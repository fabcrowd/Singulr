"""Admin API tests."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.models import Ban


@pytest.mark.asyncio
async def test_admin_bans_requires_api_key(api_client: httpx.AsyncClient) -> None:
    """GET /api/admin/bans without key returns 401."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ADMIN_API_KEY", "secret-admin-key")
        from singulr.config import get_settings

        get_settings.cache_clear()
        response = await api_client.get("/api/admin/bans")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_bans_lists_records_with_valid_key(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /api/admin/bans with X-Admin-Key returns ban list."""
    db_session.add(
        Ban(
            telegram_user_id=12345,
            fingerprint_hash="0x" + "b" * 64,
            reason="spam",
        )
    )
    await db_session.commit()

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ADMIN_API_KEY", "secret-admin-key")
        from singulr.config import get_settings

        get_settings.cache_clear()
        response = await api_client.get(
            "/api/admin/bans",
            headers={"X-Admin-Key": "secret-admin-key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["telegram_user_id"] == 12345
    assert body[0]["reason"] == "spam"
    assert "fingerprint_hash" in body[0]
