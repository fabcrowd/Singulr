"""Tests for hashing helpers."""

from __future__ import annotations

from singulr.services.hashing import hash_fingerprint, hash_ip, hash_payload, sha256_hex


def test_sha256_hex_is_deterministic() -> None:
    """Same input always yields the same digest."""
    assert sha256_hex("singulr") == sha256_hex("singulr")
    assert len(sha256_hex("singulr")) == 64


def test_hash_ip_prefixes_and_hides_raw_address() -> None:
    """IP hashes are 0x-prefixed and do not contain the raw address."""
    raw = "203.0.113.42"
    hashed = hash_ip(raw)
    assert hashed.startswith("0x")
    assert raw not in hashed
    assert hash_ip(raw) == hash_ip(raw)


def test_hash_fingerprint_includes_request_id_when_present() -> None:
    """Fingerprint hash changes when request_id is provided."""
    base = hash_fingerprint("visitor-1")
    with_request = hash_fingerprint("visitor-1", "req-abc")
    assert base != with_request
    assert hash_fingerprint("visitor-1", "req-abc") == with_request


def test_hash_payload_is_stable_for_key_order() -> None:
    """Canonical JSON sorting makes payload hashes stable."""
    first = hash_payload({"b": 2, "a": 1})
    second = hash_payload({"a": 1, "b": 2})
    assert first == second
