"""Tests for trusted proxy client IP resolution."""

from __future__ import annotations

from starlette.requests import Request

from singulr.services.client_ip import resolve_client_ip


def _request(
    *,
    peer: str = "127.0.0.1",
    x_forwarded_for: str | None = None,
) -> Request:
    """Build a minimal Starlette request for IP resolution tests."""
    headers: list[tuple[bytes, bytes]] = []
    if x_forwarded_for is not None:
        headers.append((b"x-forwarded-for", x_forwarded_for.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/verify/precheck",
        "headers": headers,
        "client": (peer, 12345),
    }
    return Request(scope)


def test_resolve_client_ip_ignores_xff_without_trusted_proxy() -> None:
    """Untrusted peers cannot spoof X-Forwarded-For."""
    request = _request(x_forwarded_for="203.0.113.99")
    assert resolve_client_ip(request, []) == "127.0.0.1"


def test_resolve_client_ip_uses_xff_from_trusted_proxy() -> None:
    """Trusted proxy peers may supply the real client via X-Forwarded-For."""
    request = _request(x_forwarded_for="203.0.113.99, 10.0.0.1")
    assert resolve_client_ip(request, ["127.0.0.1"]) == "203.0.113.99"
