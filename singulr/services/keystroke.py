"""Keystroke dynamics extraction and similarity matching."""

from __future__ import annotations

import math
from typing import Any

from singulr.services.hashing import hash_payload
from singulr.services.keystroke_validation import (
    extract_flight_times,
    flight_coefficient_of_variation,
    typing_duration_ms,
)


def rhythm_vector(keystrokes: list[dict[str, Any]], max_len: int = 64) -> list[float]:
    """Build a normalized timing vector for comparison."""
    flights = extract_flight_times(keystrokes)
    if not flights:
        return []
    if len(flights) > max_len:
        step = len(flights) / max_len
        flights = [flights[int(i * step)] for i in range(max_len)]
    mean = sum(flights) / len(flights)
    if mean <= 0:
        return flights
    return [f / mean for f in flights]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors (0–1 scale)."""
    if not a or not b:
        return 0.0
    length = min(len(a), len(b))
    a_slice = a[:length]
    b_slice = b[:length]
    dot = sum(x * y for x, y in zip(a_slice, b_slice, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a_slice))
    norm_b = math.sqrt(sum(x * x for x in b_slice))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def build_keystroke_profile(
    keystrokes: list[dict[str, Any]],
    device_type: str,
    wpm: float | None = None,
    error_count: int = 0,
) -> dict[str, Any]:
    """Package keystroke session into a storable profile."""
    flights = extract_flight_times(keystrokes)
    hold_times = [
        float(e["up"] - e["down"])
        for e in keystrokes
        if "down" in e and "up" in e and e["up"] is not None and e["down"] is not None
    ]
    profile = {
        "device_type": device_type,
        "rhythm": rhythm_vector(keystrokes),
        "wpm": wpm,
        "error_count": error_count,
        "hold_avg": sum(hold_times) / len(hold_times) if hold_times else None,
        "flight_avg": sum(flights) / len(flights) if flights else None,
        "flight_cv": flight_coefficient_of_variation(flights),
        "duration_ms": typing_duration_ms(keystrokes),
        "keystroke_count": len(keystrokes),
    }
    profile["rhythm_hash"] = hash_payload({"rhythm": profile["rhythm"], "device_type": device_type})
    return profile


def keystroke_similarity(profile_a: dict[str, Any], profile_b: dict[str, Any]) -> float:
    """Compare two keystroke profiles; device types must match for fair comparison."""
    if profile_a.get("device_type") != profile_b.get("device_type"):
        return 0.0
    vec_a = profile_a.get("rhythm") or []
    vec_b = profile_b.get("rhythm") or []
    return cosine_similarity(vec_a, vec_b)
