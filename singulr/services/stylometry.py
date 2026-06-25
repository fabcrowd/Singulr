"""Stylometry feature extraction from message text."""

from __future__ import annotations

import math
import re
from collections import Counter

from singulr.services.hashing import hash_payload

FUNCTION_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "it",
    "this",
    "that",
    "i",
    "you",
    "we",
    "they",
    "he",
    "she",
}

WORD_RE = re.compile(r"[a-zA-Z']+")
EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)


def extract_features(text: str) -> dict[str, float]:
    """Extract linguistic features from a single message."""
    if not text.strip():
        return {}
    words = [w.lower() for w in WORD_RE.findall(text)]
    word_count = max(len(words), 1)
    chars = len(text)
    sentences = max(text.count(".") + text.count("!") + text.count("?"), 1)
    emojis = EMOJI_RE.findall(text)
    func_hits = sum(1 for w in words if w in FUNCTION_WORDS)
    unique_ratio = len(set(words)) / word_count
    caps_ratio = sum(1 for c in text if c.isupper()) / max(chars, 1)
    punct_ratio = sum(1 for c in text if c in ".,!?;:") / max(chars, 1)
    lower_ratio = sum(1 for c in text if c.islower()) / max(chars, 1)
    bigrams = Counter(zip(words, words[1:], strict=False))
    top_bigram_freq = bigrams.most_common(1)[0][1] / word_count if bigrams else 0.0
    return {
        "avg_word_len": sum(len(w) for w in words) / word_count,
        "msg_len": float(chars),
        "sentence_len": float(chars / sentences),
        "func_word_ratio": func_hits / word_count,
        "unique_ratio": unique_ratio,
        "caps_ratio": caps_ratio,
        "punct_ratio": punct_ratio,
        "lower_ratio": lower_ratio,
        "emoji_rate": len(emojis) / word_count,
        "top_bigram_freq": top_bigram_freq,
    }


def merge_feature_vectors(vectors: list[dict[str, float]]) -> dict[str, float]:
    """Average feature vectors across messages."""
    if not vectors:
        return {}
    keys = vectors[0].keys()
    merged: dict[str, float] = {}
    for key in keys:
        values = [v[key] for v in vectors if key in v]
        merged[key] = sum(values) / len(values) if values else 0.0
    return merged


def stylometry_hash(feature_vector: dict[str, float]) -> str:
    """Hash stylometry vector for on-chain storage."""
    rounded = {k: round(v, 4) for k, v in sorted(feature_vector.items())}
    return hash_payload(rounded)


def stylometry_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Cosine similarity between stylometry vectors."""
    if not vec_a or not vec_b:
        return 0.0
    keys = set(vec_a.keys()) & set(vec_b.keys())
    if not keys:
        return 0.0
    a = [vec_a[k] for k in sorted(keys)]
    b = [vec_b[k] for k in sorted(keys)]
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))
