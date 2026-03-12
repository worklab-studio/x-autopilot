"""
reply_classifier.py — Classify tweets before replying.
"""

import json
from dotenv import load_dotenv
from ai.llm_client import chat_text

load_dotenv()

TWEET_TYPES = [
    "announcement",
    "opinion",
    "question",
    "personal_update",
    "win_milestone",
    "complaint",
    "joke_meme",
    "educational",
    "hot_take",
    "thread",
    "news_reaction",
]


def classify_tweet(tweet_text: str, thread_context: str = None, extra_context: str = None) -> dict:
    """
    Returns a dict with:
    - tweet_type (one of TWEET_TYPES)
    - intent_scores (react, add, answer, support, challenge, clarify, joke, skip)
    - tone
    - emotional_temperature
    - expects_discussion (bool)
    - should_skip (bool)
    """
    thread_section = f"\nTHREAD CONTEXT:\n{thread_context}" if thread_context else ""
    extra_section = f"\nEXTRA CONTEXT:\n{extra_context}" if extra_context else ""

    prompt = f"""Classify this tweet for reply strategy.

TWEET:
\"\"\"{tweet_text}\"\"\"
{thread_section}
{extra_section}

Return ONLY valid JSON with these fields:
tweet_type: one of {TWEET_TYPES}
intent_scores: object with keys react, add, answer, support, challenge, clarify, joke, skip (values 0.0-1.0)
tone: short label (e.g., neutral, playful, frustrated, excited, serious)
emotional_temperature: low | medium | high
expects_discussion: true | false
should_skip: true | false

    JSON ONLY."""

    try:
        text = chat_text(
            prompt=prompt,
            max_tokens=200,
        ).strip()
        text = text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        if data.get("tweet_type") not in TWEET_TYPES:
            data["tweet_type"] = "opinion"
        return data
    except Exception:
        return {
            "tweet_type": "opinion",
            "intent_scores": {
                "react": 0.4,
                "add": 0.4,
                "answer": 0.1,
                "support": 0.2,
                "challenge": 0.2,
                "clarify": 0.1,
                "joke": 0.05,
                "skip": 0.1,
            },
            "tone": "neutral",
            "emotional_temperature": "medium",
            "expects_discussion": False,
            "should_skip": False,
        }
