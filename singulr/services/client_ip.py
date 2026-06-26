"""Client IP resolution for rate limiting and verification hashing."""

from __future__ import annotations

from fastapi import Request


def resolve_client_ip(request: Request, trusted_proxy_ips: list[str] | None = None) -> str:
    """Return the client IP, honoring X-Forwarded-For only from trusted proxy peers."""
    peer = request.client.host if request.client else "0.0.0.0"
    trusted = set(trusted_proxy_ips or [])
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and peer in trusted:
        return forwarded.split(",")[0].strip()
    return peer
