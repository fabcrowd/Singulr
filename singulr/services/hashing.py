"""Cryptographic hashing helpers."""

import hashlib
import json
from typing import Any


def sha256_hex(value: str) -> str:
    """Return SHA-256 hex digest of a string."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_fingerprint(visitor_id: str, request_id: str | None = None) -> str:
    """Normalize FingerprintJS visitor id to a stored hash."""
    raw = f"{visitor_id}:{request_id or ''}"
    return f"0x{sha256_hex(raw)}"


def hash_ip(ip_address: str) -> str:
    """Hash client IP for storage (never store raw IP)."""
    return f"0x{sha256_hex(ip_address)}"


def hash_payload(payload: dict[str, Any]) -> str:
    """Stable hash of a JSON-serializable dict."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"0x{sha256_hex(canonical)}"
