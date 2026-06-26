"""Verify page session binding between precheck and submit."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def issue_challenge_secret() -> str:
    """Generate a one-time secret returned to the verify page at precheck."""
    return secrets.token_urlsafe(32)


def compute_challenge_proof(secret: str, *, token: str, visitor_id: str) -> str:
    """HMAC proof binding token + visitor_id to the precheck-issued secret."""
    message = f"{token}:{visitor_id}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_challenge_proof(
    secret: str | None,
    proof: str | None,
    *,
    token: str,
    visitor_id: str,
) -> bool:
    """Return True when proof matches the stored challenge secret."""
    if not secret or not proof:
        return False
    expected = compute_challenge_proof(secret, token=token, visitor_id=visitor_id)
    return hmac.compare_digest(expected, proof)
