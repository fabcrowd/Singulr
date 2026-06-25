"""Unit tests for keystroke dynamics and stylometry feature helpers."""

from __future__ import annotations

from singulr.services.keystroke import (
    build_keystroke_profile,
    extract_flight_times,
    keystroke_similarity,
)
from singulr.services.stylometry import extract_features, stylometry_similarity

_DESKTOP_KEYSTROKES = [
    {"key": "W", "down": 0, "up": 80, "flight": 0},
    {"key": "e", "down": 120, "up": 190, "flight": 40},
    {"key": "l", "down": 250, "up": 310, "flight": 60},
    {"key": "c", "down": 380, "up": 450, "flight": 70},
]

_MOBILE_KEYSTROKES = [
    {"key": "h", "down": 0, "up": 95, "flight": 0},
    {"key": "i", "down": 140, "up": 205, "flight": 45},
]


def test_extract_flight_times_collects_numeric_flights() -> None:
    """Flight times are extracted from keystroke event payloads."""
    flights = extract_flight_times(_DESKTOP_KEYSTROKES)
    assert flights == [0.0, 40.0, 60.0, 70.0]


def test_keystroke_similarity_requires_matching_device_type() -> None:
    """Different device types never compare as similar."""
    desktop_a = build_keystroke_profile(_DESKTOP_KEYSTROKES, "desktop")
    desktop_b = build_keystroke_profile(_DESKTOP_KEYSTROKES, "desktop")
    mobile = build_keystroke_profile(_MOBILE_KEYSTROKES, "mobile")

    assert keystroke_similarity(desktop_a, desktop_b) >= 0.99
    assert keystroke_similarity(desktop_a, mobile) == 0.0


def test_build_keystroke_profile_includes_rhythm_hash() -> None:
    """Profiles package rhythm stats and a stable rhythm hash."""
    profile = build_keystroke_profile(_DESKTOP_KEYSTROKES, "desktop", wpm=42.0, error_count=1)

    assert profile["device_type"] == "desktop"
    assert profile["wpm"] == 42.0
    assert profile["error_count"] == 1
    assert profile["rhythm"]
    assert profile["rhythm_hash"].startswith("0x")


def test_stylometry_extract_features_supports_similarity() -> None:
    """Feature vectors distinguish casual vs formal writing styles."""
    casual = extract_features("lol yeah whatever man")
    formal = extract_features("The committee reviewed the documentation thoroughly.")

    assert casual
    assert formal
    assert stylometry_similarity(casual, casual) == 1.0
    assert stylometry_similarity(casual, formal) < stylometry_similarity(casual, casual)
