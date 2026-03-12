"""
reply_strategy.py — Reply shape selection, ending control, and ranking helpers.
"""

import random
import re
import sqlite3
from agent.logger import DB_PATH


GENERIC_PHRASES = [
    "great post",
    "love this",
    "so true",
    "totally agree",
    "agree with this",
    "well said",
    "nice one",
    "this is gold",
]

QUESTION_WORDS = {"what", "why", "how", "when", "where", "who", "which"}


def recent_reply_texts(limit: int = 20) -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT content FROM actions
        WHERE action_type = 'reply'
        AND success = 1
        AND content IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows if r and r[0]]


def classify_ending(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "fragment"
    lower = t.lower()
    if lower.endswith("?"):
        return "question"
    if lower.endswith("!"):
        return "punchline"
    if lower.endswith("."):
        if lower.startswith(("agree", "strong take", "fair", "makes sense")):
            return "agreement_close"
        return "statement"
    if len(t.split()) <= 6:
        return "fragment"
    return "statement"


def question_ending_count(texts: list, window: int = 5) -> int:
    endings = [classify_ending(t) for t in texts[:window]]
    return sum(1 for e in endings if e == "question")


def jaccard_similarity(a: str, b: str) -> float:
    a_tokens = set(re.findall(r"[a-zA-Z0-9_']{2,}", (a or "").lower()))
    b_tokens = set(re.findall(r"[a-zA-Z0-9_']{2,}", (b or "").lower()))
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / max(len(a_tokens | b_tokens), 1)


def overlap_ratio(a: str, b: str) -> float:
    a_tokens = set(re.findall(r"[a-zA-Z0-9_']{2,}", (a or "").lower()))
    b_tokens = set(re.findall(r"[a-zA-Z0-9_']{2,}", (b or "").lower()))
    if not a_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / max(len(a_tokens), 1)


def pick_shape(distribution: dict, allowed_shapes: list) -> str:
    pool = [(k, v) for k, v in distribution.items() if k in allowed_shapes]
    if not pool:
        return allowed_shapes[0] if allowed_shapes else "statement"
    keys, weights = zip(*pool)
    return random.choices(keys, weights=weights, k=1)[0]


def rank_candidates(candidates: list, tweet_text: str, recent_texts: list, penalties: dict) -> list:
    ranked = []
    for item in candidates:
        text = (item.get("text") or "").strip()
        if not text:
            continue

        lower = text.lower()
        if any(p in lower for p in GENERIC_PHRASES):
            base = 0.2
        else:
            base = 0.6

        length = len(text.split())
        specificity = 0.5 + (0.1 if re.search(r"\d", text) else 0.0)
        specificity += 0.1 if length >= 8 else 0.0
        specificity = min(1.0, specificity)

        overlap = overlap_ratio(text, tweet_text)
        non_generic = 1.0 - min(overlap, 0.8)

        max_sim = 0.0
        for recent in recent_texts:
            max_sim = max(max_sim, jaccard_similarity(text, recent))
        variety = 1.0 - max_sim

        ending = classify_ending(text)
        question_penalty = penalties.get("question", 0.0) if ending == "question" else 0.0

        score = (
            base * 0.2
            + specificity * 0.25
            + non_generic * 0.2
            + variety * 0.2
            + 0.15
        ) - question_penalty

        ranked.append((score, {**item, "ending": ending}))

    ranked.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in ranked]
