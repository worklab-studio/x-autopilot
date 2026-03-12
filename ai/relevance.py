"""
relevance.py — Lightweight embedding + similarity helpers.
Uses feature hashing to avoid heavy dependencies.
"""

import hashlib
import math
import re


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]{2,}")


def _tokenize(text: str) -> list:
    if not text:
        return []
    return TOKEN_RE.findall(text.lower())


def text_to_embedding(text: str, dims: int = 256) -> list:
    vec = [0.0] * dims
    tokens = _tokenize(text)
    if not tokens:
        return vec
    for token in tokens:
        h = hashlib.md5(token.encode("utf-8")).hexdigest()
        idx = int(h[:8], 16) % dims
        vec[idx] += 1.0
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine_similarity(a: list, b: list) -> float:
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def topic_signature(text: str, max_tokens: int = 6) -> str:
    tokens = _tokenize(text)
    freq = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    top = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:max_tokens]
    return "|".join([t for t, _ in top])
