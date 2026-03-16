"""
quality.py — Candidate quality scoring and relevance helpers.
Shared across reply/like/follow for consistent filtering.
"""

import re
from ai.relevance import text_to_embedding, cosine_similarity


WORD_RE = re.compile(r"[a-zA-Z0-9_']{2,}")


def _tokens(text: str) -> list:
    if not text:
        return []
    return WORD_RE.findall(text.lower())


def relevance_keywords(config: dict) -> list:
    keywords = set()
    for topic in config.get("content_topics", []):
        keywords.add(topic.lower())
        for part in topic.lower().split():
            if len(part) > 2:
                keywords.add(part)

    niche = config.get("voice", {}).get("niche", "")
    for chunk in niche.split(","):
        chunk = chunk.strip().lower()
        if chunk:
            keywords.add(chunk)

    for kw in config.get("discovery", {}).get("relevance_keywords", []):
        if kw:
            keywords.add(kw.lower())

    return list(keywords)


def build_relevance_profile(config: dict) -> str:
    voice = config.get("voice", {})
    parts = []
    for key in ["niche", "product", "personality"]:
        if voice.get(key):
            parts.append(str(voice.get(key)))
    parts.extend(config.get("content_topics", []))
    return " | ".join(parts)


def embedding_score(text: str, profile_text: str) -> float:
    if not text or not profile_text:
        return 0.0
    return cosine_similarity(
        text_to_embedding(text),
        text_to_embedding(profile_text)
    )


def is_relevant(text: str, keywords: list) -> bool:
    if not keywords:
        return True
    text_lower = (text or "").lower()
    return any(k in text_lower for k in keywords)


def is_bait(text: str, config: dict) -> bool:
    lower = (text or "").lower()
    for phrase in config.get("discovery", {}).get("skip_bait_phrases", []):
        if phrase and phrase in lower:
            return True
    return False


try:
    from langdetect import detect as _ld_detect
    _HAVE_LANGDETECT = True
except ImportError:
    _HAVE_LANGDETECT = False


def is_english(text: str) -> bool:
    if not text or not text.strip():
        return False
    clean = text.strip()
    # Short text (< 20 chars): langdetect is unreliable — use ASCII ratio only
    if len(clean) < 20:
        letters = [c for c in clean if c.isalpha()]
        if not letters:
            return True   # emoji / punctuation only — don't block
        ascii_l = [c for c in letters if ord(c) < 128]
        return len(ascii_l) / len(letters) >= 0.85
    # Longer text: use langdetect (accurate), fall back to tightened heuristic
    if _HAVE_LANGDETECT:
        try:
            return _ld_detect(clean) == "en"
        except Exception:
            pass  # fall through to heuristic
    # Fallback heuristic (tightened from original)
    letters = [c for c in clean if c.isalpha()]
    if not letters:
        return False
    ascii_l = [c for c in letters if ord(c) < 128]
    if len(ascii_l) / len(letters) < 0.80:  # raised from 0.70
        return False
    lower = f" {clean.lower()} "
    common = [" the ", " and ", " to ", " of ", " in ", " for ", " with ", " on ",
              " is ", " are ", " was ", " it ", " that ", " this ", " have "]
    hits = sum(1 for w in common if w in lower)
    return hits >= 2  # raised from 1


def is_low_engagement(tweet: dict, config: dict) -> bool:
    discovery = config.get("discovery", {})
    counts = tweet.get("engagement") or {}
    likes = counts.get("likes", 0)
    replies = counts.get("replies", 0)
    retweets = counts.get("retweets", 0)
    total = likes + replies + retweets

    if total < discovery.get("min_total_engagement", 0):
        return True
    if likes < discovery.get("min_likes", 0):
        return True
    if replies < discovery.get("min_replies", 0):
        return True
    if retweets < discovery.get("min_retweets", 0):
        return True
    return False


def _engagement_score(tweet: dict, config: dict) -> float:
    if is_low_engagement(tweet, config):
        return 0.0
    counts = tweet.get("engagement") or {}
    total = counts.get("likes", 0) + counts.get("replies", 0) + counts.get("retweets", 0)
    min_total = config.get("discovery", {}).get("min_total_engagement", 0)
    if min_total <= 0:
        return 1.0 if total > 0 else 0.6
    return min(1.0, total / max(min_total, 1))


def text_quality_score(text: str, config: dict) -> float:
    words = _tokens(text)
    if not words:
        return 0.0

    discovery = config.get("discovery", {})
    min_words = discovery.get("candidate_min_words", 6)
    min_unique_ratio = discovery.get("candidate_min_unique_ratio", 0.45)

    unique_ratio = len(set(words)) / max(len(words), 1)
    length_score = min(1.0, len(words) / max(min_words, 1))
    ratio_score = min(1.0, unique_ratio / max(min_unique_ratio, 0.01))

    return (length_score * 0.6) + (ratio_score * 0.4)


def candidate_score(
    text: str,
    tweet: dict,
    config: dict,
    profile_text: str = None,
    keywords: list = None
) -> float:
    discovery = config.get("discovery", {})
    keywords = keywords if keywords is not None else relevance_keywords(config)
    profile_text = profile_text if profile_text is not None else build_relevance_profile(config)

    keyword_hit = is_relevant(text, keywords)
    keyword_score = 1.0 if keyword_hit else 0.0

    use_embeddings = discovery.get("use_embeddings", False)
    embed_score = embedding_score(text, profile_text) if use_embeddings else (0.6 if keyword_hit else 0.4)

    engagement_score = _engagement_score(tweet, config)
    quality_score = text_quality_score(text, config)

    score = (embed_score * 0.45) + (keyword_score * 0.2) + (engagement_score * 0.2) + (quality_score * 0.15)

    if discovery.get("require_keyword_match", False) and not keyword_hit:
        score *= 0.2

    return score


def candidate_passes(
    text: str,
    tweet: dict,
    config: dict,
    profile_text: str = None,
    keywords: list = None
) -> tuple:
    threshold = config.get("discovery", {}).get("candidate_score_threshold", 0.0)
    score = candidate_score(text, tweet, config, profile_text=profile_text, keywords=keywords)
    return score >= threshold, score


def thread_topic_ratio(
    thread_text: str,
    config: dict,
    profile_text: str = None,
    keywords: list = None
) -> float:
    parts = [p.strip() for p in re.split(r"[\\n\\.!?]+", thread_text or "") if p.strip()]
    if not parts:
        return 0.0

    discovery = config.get("discovery", {})
    keywords = keywords if keywords is not None else relevance_keywords(config)
    profile_text = profile_text if profile_text is not None else build_relevance_profile(config)
    use_embeddings = discovery.get("use_embeddings", False)
    threshold = discovery.get("embedding_threshold", 0.0)

    matches = 0
    for part in parts:
        if is_relevant(part, keywords):
            matches += 1
            continue
        if use_embeddings and embedding_score(part, profile_text) >= threshold:
            matches += 1

    return matches / max(len(parts), 1)
