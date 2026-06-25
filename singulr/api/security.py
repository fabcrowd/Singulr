"""Shared API authentication helpers."""

from __future__ import annotations

from fastapi import Header, HTTPException

from singulr.config import get_settings


def require_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    """Reject requests without a valid admin API key."""
    expected = get_settings().admin_api_key
    if not expected:
        raise HTTPException(status_code=503, detail="admin_api_disabled")
    if not x_admin_key or x_admin_key != expected:
        raise HTTPException(status_code=401, detail="unauthorized")
