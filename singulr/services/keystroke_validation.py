"""Keystroke plausibility checks for verify submit."""

from __future__ import annotations

import json
import math
from typing import Any

MAX_KEYSTROKES = 500
MAX_SUBMIT_BODY_BYTES = 65_536
MIN_TYPING_DURATION_MS = 3_000
MIN_FLIGHT_CV = 0.08


def extract_flight_times(keystrokes: list[dict[str, Any]]) -> list[float]:
    """Extract inter-key flight times in milliseconds from raw events."""
    flights: list[float] = []
    for event in keystrokes:
        flight = event.get("flight")
        if flight is not None and isinstance(flight, (int, float)):
            flights.append(float(flight))
    return flights


def flight_coefficient_of_variation(flights: list[float]) -> float | None:
    """Return coefficient of variation for flight times, or None when undefined."""
    if len(flights) < 2:
        return None
    mean = sum(flights) / len(flights)
    if mean <= 0:
        return None
    variance = sum((value - mean) ** 2 for value in flights) / len(flights)
    return math.sqrt(variance) / mean


def typing_duration_ms(keystrokes: list[dict[str, Any]]) -> float | None:
    """Estimate session duration from the last key-up or key-down timestamp."""
    timestamps: list[float] = []
    for event in keystrokes:
        for field in ("up", "down"):
            value = event.get(field)
            if isinstance(value, (int, float)):
                timestamps.append(float(value))
    if not timestamps:
        return None
    return max(timestamps) - min(timestamps)


def is_synthetic_keystroke_rhythm(keystrokes: list[dict[str, Any]]) -> bool:
    """True when inter-key flight times are unnaturally uniform."""
    flights = extract_flight_times(keystrokes)
    if len(flights) < 4:
        return False
    cv = flight_coefficient_of_variation(flights)
    return cv is not None and cv < MIN_FLIGHT_CV


def is_too_fast_typing(keystrokes: list[dict[str, Any]]) -> bool:
    """True when the typed session completes faster than a human floor."""
    if len(keystrokes) < 3:
        return False
    duration = typing_duration_ms(keystrokes)
    return duration is not None and duration < MIN_TYPING_DURATION_MS


def keystroke_risk_factors(keystrokes: list[dict[str, Any]]) -> list[str]:
    """Return risk factor labels for implausible keystroke sessions."""
    factors: list[str] = []
    if is_synthetic_keystroke_rhythm(keystrokes):
        factors.append("synthetic_keystroke")
    if is_too_fast_typing(keystrokes):
        factors.append("too_fast_verify")
    return factors


def keystroke_risk_factors_from_profile(profile: dict[str, Any]) -> list[str]:
    """Derive keystroke risk labels from a built keystroke profile."""
    factors: list[str] = []
    if profile.get("keystroke_count", 0) >= 4:
        cv = profile.get("flight_cv")
        if cv is not None and cv < MIN_FLIGHT_CV:
            factors.append("synthetic_keystroke")
    duration = profile.get("duration_ms")
    if profile.get("keystroke_count", 0) >= 3 and duration is not None and duration < MIN_TYPING_DURATION_MS:
        factors.append("too_fast_verify")
    return factors


def submit_body_too_large(payload: dict[str, Any]) -> bool:
    """True when serialized submit JSON exceeds the configured byte cap."""
    return len(json.dumps(payload, separators=(",", ":")).encode()) > MAX_SUBMIT_BODY_BYTES
