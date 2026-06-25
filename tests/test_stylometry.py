"""Tests for stylometry profile accumulation."""

from __future__ import annotations

from singulr.services.stylometry import (
    extract_features,
    merge_feature_vectors,
    stylometry_similarity,
)

AUTHOR_A_MESSAGES = [
    "lol yeah",
    "nah idk",
    "whatever man",
    "yeah sure lol",
]

AUTHOR_A_HOLDOUT = [
    "lol nah",
    "idk yeah",
]

AUTHOR_B_MESSAGES = [
    "The committee has reviewed the documentation thoroughly.",
    "All stakeholders must comply with the established guidelines.",
    "Please submit your report by the end of the business day.",
    "The quarterly assessment will proceed as scheduled.",
]


def _merged_profile(messages: list[str]) -> dict[str, float]:
    """Build an averaged stylometry profile from multiple messages."""
    return merge_feature_vectors([extract_features(message) for message in messages])


def test_merge_feature_vectors_same_author_similarity_exceeds_different_author() -> None:
    """Merged same-author profiles should score higher than merged cross-author profiles."""
    profile_a = _merged_profile(AUTHOR_A_MESSAGES)
    profile_a_holdout = _merged_profile(AUTHOR_A_HOLDOUT)
    profile_b = _merged_profile(AUTHOR_B_MESSAGES)

    same_author_similarity = stylometry_similarity(profile_a, profile_a_holdout)
    different_author_similarity = stylometry_similarity(profile_a, profile_b)

    assert same_author_similarity > different_author_similarity


def test_merge_feature_vectors_improves_author_discrimination() -> None:
    """Averaging several messages widens the gap between same- and cross-author similarity."""
    profile_a = _merged_profile(AUTHOR_A_MESSAGES)
    profile_a_holdout = _merged_profile(AUTHOR_A_HOLDOUT)
    profile_b = _merged_profile(AUTHOR_B_MESSAGES)

    single_message = extract_features("yeah sure lol")
    single_gap = stylometry_similarity(single_message, profile_a_holdout) - stylometry_similarity(
        single_message, profile_b
    )
    merged_gap = stylometry_similarity(profile_a, profile_a_holdout) - stylometry_similarity(
        profile_a, profile_b
    )

    assert merged_gap > single_gap


def test_extract_features_returns_empty_for_blank_message() -> None:
    """Blank channel messages produce no stylometry features."""
    assert extract_features("") == {}
    assert extract_features("   ") == {}
