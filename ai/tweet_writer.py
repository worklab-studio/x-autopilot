"""
tweet_writer.py — Generates tweets in your exact voice
Uses Claude to write tweets based on your voice profile,
trends, and content strategy.
"""

import os
import re
import json
import random
import sqlite3
from ai.reply_classifier import classify_tweet
from ai.reply_strategy import (
    recent_reply_texts,
    classify_ending,
    question_ending_count,
    pick_shape,
    rank_candidates,
)
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from agent.logger import DB_PATH
from ai.relevance import topic_signature
from agent.dynamic_config import load_config_with_dynamic
from ai.llm_client import chat_text

load_dotenv()

VOICE_PROFILE_PATH = Path(__file__).parent / "voice_profile.txt"
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

TOKEN_RE = re.compile(r"[a-zA-Z0-9_]{2,}")
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "over", "than",
    "just", "most", "more", "less", "your", "their", "they", "them", "was", "were",
    "are", "you", "our", "out", "has", "have", "had", "but", "not", "its", "it's",
    "about", "what", "when", "where", "why", "how", "then", "now", "only", "also",
    "too", "very", "can", "cant", "can't", "could", "should", "would", "will",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
}

TWEET_TEMPLATES = [
    {
        "name": "tension_insight_close",
        "instruction": "Structure: tension line -> single insight -> dry close. 3 short parts.",
    },
    {
        "name": "observation_why_example",
        "instruction": "Structure: observation -> why it matters -> specific example.",
    },
    {
        "name": "counterpoint_constraint_close",
        "instruction": "Structure: counterpoint -> constraint -> nuanced close.",
    },
    {
        "name": "compressed_system_step",
        "instruction": "Structure: compressed system -> one practical step. No extra fluff.",
    },
    {
        "name": "number_insight",
        "instruction": "Start with a specific number or metric. Build the insight around it. End on a dry observation.",
    },
    {
        "name": "vulnerability_take",
        "instruction": "Open with a failure or mistake. State what it revealed. End with the rule that came from it.",
    },
    {
        "name": "build_update",
        "instruction": "One concrete build update with a real number. State what changed. One dry close — no CTA.",
    },
]

THREAD_TEMPLATES = [
    {
        "name": "field_note",
        "instruction": "Field Note: problem -> what you tried -> what broke -> new rule. Hook is the problem stated with one specific detail.",
    },
    {
        "name": "mechanics",
        "instruction": "Mechanics: concept -> 3-step system -> pitfalls -> one crisp takeaway. Hook names the system with a specific metric.",
    },
    {
        "name": "counter_intuitive",
        "instruction": "Counter-intuitive: common belief -> why it fails -> your alternative -> real example. Hook states the counter-intuitive thing as fact.",
    },
    {
        "name": "before_after",
        "instruction": "Hook: state what changed (use a number or metric). Then: what you did before -> the moment of shift -> what changed -> how to apply it. Each tweet earns the next.",
    },
    {
        "name": "myth_busting",
        "instruction": "Hook: name the biggest myth in one line. Each subsequent tweet busts one specific myth with a counter-example or real number. End: the actual truth in one crisp sentence.",
    },
    {
        "name": "step_by_step",
        "instruction": "Hook: state the outcome in one line with a specific metric. Each tweet = one step with concrete detail. No fluff. End: the trap most people fall into at the last step.",
    },
    {
        "name": "hot_take_thread",
        "instruction": "Hook: unpopular opinion stated as fact. Next: why most people believe the wrong thing. Then: evidence or personal example with a real number. End: what to do instead.",
    },
    {
        "name": "build_in_public",
        "instruction": "Hook: specific metric or milestone (revenue, users, days). Next: what you tried -> what broke -> what surprised you. End: one rule you now live by.",
    },
]

# Hook patterns injected into prompts for engagement-optimized content
HOOK_PATTERNS = """
HOOK PATTERNS (pick the strongest one for this topic):
1. Specific number + outcome — "I went from X to Y by doing Z"
2. Unpopular opinion stated as fact — "Most [audience] do [thing] wrong."
3. Curiosity gap — state the result, withhold the method
4. Vulnerability opener — "I failed [N] times before I understood this:"
5. Counter-intuitive fact with a real number
6. Bold specific claim tied to a concrete scenario (not vague)
The hook must make someone stop scrolling. It must not be generic.
"""


def load_voice_profile() -> str:
    with open(VOICE_PROFILE_PATH, "r") as f:
        return f.read()


def load_config() -> dict:
    return load_config_with_dynamic(CONFIG_PATH)


def _enforce_line_breaks(text: str) -> str:
    if "\n" in text or len(text) < 120:
        return text

    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(parts) <= 1:
        return text

    if len(text) > 200 and len(parts) >= 3:
        third = max(1, len(parts) // 3)
        chunks = [
            " ".join(parts[:third]),
            " ".join(parts[third:2 * third]),
            " ".join(parts[2 * third:]),
        ]
    else:
        mid = len(parts) // 2
        chunks = [
            " ".join(parts[:mid]),
            " ".join(parts[mid:]),
        ]

    chunks = [c.strip() for c in chunks if c.strip()]
    if len(chunks) <= 1:
        return text

    return "\n\n".join(chunks)


def _listify(value) -> list:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        parts = []
        for line in value.replace("\r", "\n").split("\n"):
            parts.extend([v.strip() for v in line.split(",") if v.strip()])
        return parts
    return []


def _pick_one(values: list) -> str:
    values = _listify(values)
    return random.choice(values) if values else ""


def _tokenize(text: str) -> list:
    return TOKEN_RE.findall((text or "").lower())


def _normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^a-z0-9\s@#%$]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _ngram_set(tokens: list, n: int = 3) -> set:
    if len(tokens) < n:
        return set()
    return {" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def _recent_post_texts(limit: int = 30) -> list:
    if limit <= 0:
        return []
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT content FROM actions
        WHERE action_type = 'tweet' AND success = 1 AND content IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows if r and r[0]]


def _is_too_similar(candidate: str, past_texts: list, threshold: float = 0.35) -> bool:
    if not candidate or not past_texts:
        return False
    cand_norm = _normalize_text(candidate)
    cand_tokens = _tokenize(cand_norm)
    cand_sig = topic_signature(candidate)
    cand_ngrams = _ngram_set(cand_tokens, 3)

    for past in past_texts:
        past_norm = _normalize_text(past)
        if not past_norm:
            continue
        if past_norm == cand_norm:
            return True
        if cand_sig and cand_sig == topic_signature(past):
            return True
        past_tokens = _tokenize(past_norm)
        jac = _jaccard(set(cand_tokens), set(past_tokens))
        if jac >= threshold:
            return True
        if cand_ngrams:
            past_ngrams = _ngram_set(past_tokens, 3)
            if past_ngrams:
                overlap = len(cand_ngrams & past_ngrams) / max(1, len(cand_ngrams))
                if overlap >= 0.3:
                    return True
    return False


def _extract_keywords(text: str, max_words: int = 6) -> list:
    tokens = _tokenize(text)
    digits = re.findall(r"\d+(?:\.\d+)?", text or "")
    keywords = [t for t in tokens if t not in STOPWORDS]
    keywords = digits + keywords
    return keywords[:max_words]


TWEET_IDEAS_PATH = Path(__file__).parent.parent / "data" / "tweet_ideas.txt"


def _get_next_idea():
    """Return the oldest unused idea from tweet_ideas.txt and mark it used."""
    if not TWEET_IDEAS_PATH.exists():
        return None
    try:
        lines = TWEET_IDEAS_PATH.read_text(encoding="utf-8").splitlines()
        updated = []
        found = None
        today = datetime.now().strftime("%Y-%m-%d")
        for line in lines:
            stripped = line.strip()
            if found is None and stripped and not stripped.startswith("#"):
                found = stripped
                updated.append(f"# USED: {today} — {stripped}")
            else:
                updated.append(line)
        if found is not None:
            TWEET_IDEAS_PATH.write_text("\n".join(updated) + "\n", encoding="utf-8")
        return found
    except Exception:
        return None


def get_ideas_list() -> list:
    """Return all unused ideas from tweet_ideas.txt."""
    if not TWEET_IDEAS_PATH.exists():
        return []
    try:
        lines = TWEET_IDEAS_PATH.read_text(encoding="utf-8").splitlines()
        return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    except Exception:
        return []


def add_idea(idea: str):
    """Append a new idea to tweet_ideas.txt."""
    idea = idea.strip()
    if not idea:
        return
    TWEET_IDEAS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TWEET_IDEAS_PATH, "a", encoding="utf-8") as f:
        f.write(f"{idea}\n")


def _has_specifics(text: str, proof_keywords: list, mention_handles: list) -> bool:
    lowered = (text or "").lower()
    if re.search(r"\d", lowered):
        return True
    if "@" in lowered:
        return True
    if re.search(r"[%$]|\b(k|m|bps|ms|sec|secs|min|mins|hrs|hours)\b", lowered):
        return True
    if "http://" in lowered or "https://" in lowered:
        return True
    for keyword in proof_keywords or []:
        if keyword and keyword in lowered:
            return True
    for handle in mention_handles or []:
        if handle and handle.lower() in lowered:
            return True
    return False


def _banned_opener(text: str) -> bool:
    banned = [
        "here's what i learned",
        "here is what i learned",
        "most founders",
        "most people",
        "a thread",
        "thread:",
        "hot take",
    ]
    lowered = (text or "").strip().lower()
    return any(lowered.startswith(prefix) for prefix in banned)


def _quality_check(tweet: str, voice: str) -> dict:
    """
    Run an AI quality check on a tweet against the voice profile.
    Scores hook strength, voice match, and engagement potential.
    Returns: {hook: int, voice_match: int, engagement: int, pass: bool, reason: str}
    """
    # Hard-fail checks before calling AI (fast, no tokens)
    if not tweet or not tweet.strip():
        return {"hook": 0, "voice_match": 0, "engagement": 0, "pass": False, "reason": "empty tweet"}

    lower = tweet.lower()
    if any(w in lower for w in ["http://", "https://"]):
        return {"hook": 0, "voice_match": 0, "engagement": 0, "pass": False, "reason": "contains URL (links go in replies)"}
    if "#" in tweet and any(f"#{w}" in lower for w in ["twitter", "x", "ai", "saas", "startup", "indiehacker", "buildinpublic"]):
        return {"hook": 0, "voice_match": 0, "engagement": 0, "pass": False, "reason": "contains hashtags"}

    prompt = f"""You are a senior Twitter content strategist evaluating a tweet for an indie hacker account.

TWEET TO EVALUATE:
\"\"\"{tweet}\"\"\"

VOICE PROFILE:
{voice}

Score this tweet on 3 dimensions from 1-10:

1. HOOK (1-10): Does the first line stop the scroll? Does it create tension, curiosity, counter-intuition, or a specific claim?
   - 9-10: Irresistible, would stop most scrollers
   - 7-8: Good, clearly non-generic
   - 5-6: Decent but forgettable
   - 1-4: Generic, vague, or clichéd

2. VOICE_MATCH (1-10): Does it sound exactly like the voice profile? Tone, rhythm, word choice, no motivational fluff, dry/specific close?
   - 9-10: Indistinguishable from the real account
   - 7-8: Clearly in voice
   - 5-6: Mostly on voice but with some off notes
   - 1-4: Doesn't match the voice profile

3. ENGAGEMENT (1-10): Will this earn replies, bookmarks, or retweets — not just passive likes?
   - 9-10: Will definitely spark conversation or saves
   - 7-8: Likely to earn real engagement
   - 5-6: Might get some likes but not much depth
   - 1-4: Likely to be scrolled past

Respond ONLY with valid JSON, no markdown:
{{"hook": <int>, "voice_match": <int>, "engagement": <int>, "reason": "<one sentence on the biggest weakness, or 'passes all checks' if all >= 7>"}}"""

    try:
        raw = chat_text(prompt=prompt, max_tokens=120).strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        scores = json.loads(raw)
        hook = int(scores.get("hook", 0))
        voice_match = int(scores.get("voice_match", 0))
        engagement = int(scores.get("engagement", 0))
        passes = hook >= 7 and voice_match >= 7 and engagement >= 7
        return {
            "hook": hook,
            "voice_match": voice_match,
            "engagement": engagement,
            "pass": passes,
            "reason": scores.get("reason", "") if not passes else "",
        }
    except Exception:
        # If quality check fails (parse error etc.), don't block generation
        return {"hook": 7, "voice_match": 7, "engagement": 7, "pass": True, "reason": ""}


def _validate_tweet(
    text: str,
    config: dict,
    proof_point: str,
    allow_question: bool,
    recent_texts: list,
) -> tuple:
    strategy = (config or {}).get("content_strategy", {})
    if not text:
        return False, "empty"
    if _banned_opener(text):
        return False, "banned opener"

    if strategy.get("enforce_no_question", True) and not allow_question and "?" in text:
        return False, "question not allowed"

    proof_required = bool(strategy.get("require_proof", True)) and bool(proof_point)
    proof_keywords = _extract_keywords(proof_point) if proof_point else []

    if proof_required:
        if not proof_keywords:
            return False, "proof missing keywords"
        if not any(k in (text or "").lower() for k in proof_keywords):
            return False, "proof not referenced"

    if strategy.get("require_specificity", True):
        mention_cfg = (config or {}).get("mentions", {})
        mention_handles = [h for h in _listify(mention_cfg.get("tools")) if h.startswith("@")]
        if not _has_specifics(text, proof_keywords, mention_handles):
            return False, "no specific detail"

    if strategy.get("enforce_uniqueness", True):
        threshold = float(strategy.get("uniqueness_similarity_threshold", 0.35) or 0.35)
        if _is_too_similar(text, recent_texts, threshold=threshold):
            return False, "too similar to recent posts"

    return True, ""


def _validate_thread(
    tweets: list,
    config: dict,
    proof_point: str,
    allow_question: bool,
    recent_texts: list,
) -> tuple:
    strategy = (config or {}).get("content_strategy", {})
    combined = " ".join([t for t in tweets if t]).strip()
    if not combined:
        return False, "empty"
    if _banned_opener(tweets[0] if tweets else ""):
        return False, "banned opener"
    if strategy.get("enforce_no_question", True) and not allow_question and "?" in combined:
        return False, "question not allowed"

    proof_required = bool(strategy.get("require_proof", True)) and bool(proof_point)
    proof_keywords = _extract_keywords(proof_point) if proof_point else []
    if proof_required:
        if not proof_keywords:
            return False, "proof missing keywords"
        if not any(k in combined.lower() for k in proof_keywords):
            return False, "proof not referenced"

    if strategy.get("require_specificity", True):
        mention_cfg = (config or {}).get("mentions", {})
        mention_handles = [h for h in _listify(mention_cfg.get("tools")) if h.startswith("@")]
        if not _has_specifics(combined, proof_keywords, mention_handles):
            return False, "no specific detail"

    if strategy.get("enforce_uniqueness", True):
        threshold = float(strategy.get("uniqueness_similarity_threshold", 0.35) or 0.35)
        if _is_too_similar(combined, recent_texts, threshold=threshold):
            return False, "too similar to recent posts"

    return True, ""


def generate_tweet(
    topic: str = None,
    tweet_type: str = "auto",
    trend_context: str = None,
    build_update: str = None
) -> str:
    """
    Generate a tweet in your voice.

    Args:
        topic: What to tweet about (optional — agent can decide)
        tweet_type: "hot_take" | "build_update" | "resource" | "personal" | "auto"
        trend_context: What's trending right now in your niche
        build_update: Specific update from your SaaS (revenue, users, feature, etc.)
    """
    voice = load_voice_profile()
    config = load_config()
    strategy = config.get("content_strategy", {})
    recent_texts = _recent_post_texts(int(strategy.get("uniqueness_window", 30) or 30))
    allow_question = tweet_type == "question"
    max_attempts = int(strategy.get("max_generation_attempts", 4) or 4)

    all_pillars = _listify(strategy.get("voice_pillars"))
    # Pillar rotation: exclude pillars used in the last 2 days
    try:
        from agent.logger import get_recent_pillars
        recent_pillars = get_recent_pillars(days=2)
        available_pillars = [p for p in all_pillars if p not in recent_pillars]
        if not available_pillars:
            available_pillars = all_pillars  # Fall back to all if all used
    except Exception:
        available_pillars = all_pillars
    pillar = _pick_one(available_pillars)

    angle = _pick_one(strategy.get("signature_angles"))
    proof_point = _pick_one(strategy.get("proof_bank"))
    weekly_direction = _listify(strategy.get("weekly_direction"))
    weekly_block = "\n".join([f"- {d}" for d in weekly_direction[:6]]) if weekly_direction else ""

    template = {"name": "freeform", "instruction": "Freeform, still obey all rules."}
    if bool(strategy.get("tweet_templates_enabled", True)) and TWEET_TEMPLATES:
        template = random.choice(TWEET_TEMPLATES)

    # Check tweet ideas inbox first (oldest unused idea takes priority)
    if not topic:
        idea_topic = _get_next_idea()
        if idea_topic:
            topic = idea_topic

    # Build context
    day_of_week = datetime.now().strftime("%A")
    hour = datetime.now().hour
    time_of_day = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"

    trend_section = f"\nCURRENT TRENDS IN YOUR NICHE:\n{trend_context}" if trend_context else ""
    build_section = f"\nBUILD UPDATE TO WORK WITH:\n{build_update}" if build_update else ""
    topic_section = f"\nTOPIC TO TWEET ABOUT: {topic}" if topic else ""

    type_instruction = {
        "hot_take": "Write a HOT TAKE or contrarian opinion. Short, punchy, makes people think.",
        "build_update": "Write a BUILD IN PUBLIC update. Specific numbers, real details, honest.",
        "resource": "Write a PRACTICAL RESOURCE tweet. Clean list format, one line of context, no fluff after.",
        "personal": "Write a PERSONAL OBSERVATION or lesson. Something real from your building journey.",
        "auto": "Decide the best tweet type for right now and write it."
    }.get(tweet_type, "Write a tweet in your natural voice.")

    prompt_base = f"""You are a ghostwriter for an indie hacker and product designer.

Your job is to write ONE tweet that sounds indistinguishable from them.

Read their full voice profile carefully before writing. Every word must align with it.

VOICE PROFILE:
{voice}

CONTEXT:
Trend signals: {trend_section}
Current build context: {build_section}
Topic focus: {topic_section}

VOICE PILLAR (use exactly one):
{pillar or "general building"}

SIGNATURE ANGLE:
{angle or "none"}

PROOF POINT (must be referenced with at least one concrete detail):
{proof_point or "none"}

WEEKLY DIRECTION (optional anchors):
{weekly_block or "none"}

TEMPLATE TO FOLLOW:
{template["instruction"]}

INSTRUCTION:
{type_instruction}

{HOOK_PATTERNS}

STRICT RULES:

Hard limit: 280 characters.

The first line must stop the scroll — use one of the hook patterns above.

One core idea only.

The idea must feel non-obvious.

Avoid surface-level takes.

Make it practical when possible. Include specifics, systems, or mechanics.

Do not restate common indie hacker advice.

No hashtags.

No emojis unless dry and intentional. Never rockets.

No em dashes.

No motivational tone.

No "Here's what I learned" framing.

No external URLs in the tweet body.

End on insight or a subtle dry close. Never a CTA.

It must read like a real thought, not a content strategy.

Write for replies and bookmarks — not just likes. The best tweets start conversations.

Hard filters:
- Must include a specific noun, number, tool, metric, or concrete scenario.
- Use the proof point explicitly (paraphrase ok, keep at least one concrete detail).
- Do not open with banned generic phrases (e.g. "Most founders", "Here's what I learned").
- No questions unless explicitly requested as a question-type tweet.

DEPTH FILTER (apply silently before output):

Is this something 80% of Twitter already believes?
If yes, discard and rethink.

Does this introduce a new framing or mental model?

Does this reflect systems thinking?

Would a serious builder pause and think?

If it feels obvious, rewrite it.

OUTPUT:
Write ONLY the tweet text.
No explanation.
No quotes."""
    last_reason = ""
    tweet = ""
    quality_scores = None
    for _ in range(max_attempts):
        avoid_line = f"\nAVOID THIS ISSUE:\n{last_reason}\n" if last_reason else ""
        prompt = f"{prompt_base}{avoid_line}"
        tweet = chat_text(
            prompt=prompt,
            max_tokens=300,
        ).strip().replace("—", "-")
        tweet = _enforce_line_breaks(tweet)
        tweet = _trim_to_sentence(tweet, 280)

        # AI quality gate — check hook, voice match, engagement
        qc = _quality_check(tweet, voice)
        if not qc["pass"]:
            last_reason = f"Quality check failed — {qc['reason']}"
            continue

        ok, reason = _validate_tweet(
            tweet,
            config,
            proof_point,
            allow_question,
            recent_texts,
        )
        if ok:
            quality_scores = qc
            # Log pillar used for rotation tracking
            if pillar:
                try:
                    from agent.logger import log_tweet_pillar
                    log_tweet_pillar(pillar)
                except Exception:
                    pass
            return tweet
        last_reason = reason or "failed validation"

    return tweet


def generate_promo_tweet(promotion: dict) -> str:
    """
    Generate a subtle, non-salesy promo tweet for a product.
    """
    voice = load_voice_profile()
    name = promotion.get("name")
    url = promotion.get("url")
    context = promotion.get("context")

    prompt = f"""You are a ghostwriter for an indie hacker and designer.
Write ONE subtle, organic tweet that mentions a product they built.

PRODUCT:
Name: {name}
URL: {url}
Context (use this to ground the tweet): {context}

VOICE PROFILE:
{voice}

RULES:
1. Under 280 characters
2. Subtle and non-salesy — no hard CTA, no "buy", no "check out", no "launch"
3. Sound like a personal note or build observation
4. Include the URL naturally (once)
5. No hashtags
6. Never use em dashes (—)

OUTPUT: Write ONLY the tweet text. Nothing else."""

    tweet = chat_text(
        prompt=prompt,
        max_tokens=260,
    ).strip().replace("—", "-")
    tweet = _enforce_line_breaks(tweet)
    return _trim_to_sentence(tweet, 280)


def generate_from_prompt(prompt: str, format: str = "tweet") -> "str | list":
    """
    Generate a tweet or thread from a user-supplied free-text prompt.
    Enforces strong hooks and engagement-optimized structure.

    Args:
        prompt: What the user wants to write about
        format: "tweet" or "thread"
    """
    if format == "thread":
        return generate_thread(topic=prompt)
    else:
        return generate_tweet(topic=prompt)


def generate_tweet_variants(n: int = 3, **kwargs) -> list:
    """
    Generate N tweet variants in one call by running generate_tweet() N times
    with different random template/pillar selections.

    Returns a list of up to N tweet strings.
    """
    variants = []
    seen = set()
    attempts = 0
    max_attempts = n * 3  # Allow retries for uniqueness

    while len(variants) < n and attempts < max_attempts:
        attempts += 1
        tweet = generate_tweet(**kwargs)
        if tweet and tweet not in seen:
            seen.add(tweet)
            variants.append(tweet)

    return variants


def generate_thread_hooks(topic: str, n: int = 3) -> list:
    """
    Generate N hook options for the first tweet of a thread.
    Each hook uses a different style: provocative, counter-intuitive, bold claim.
    User picks one, then the full thread is generated around it.

    Returns a list of hook strings.
    """
    voice = load_voice_profile()
    config = load_config()
    strategy = config.get("content_strategy", {})

    pillar = _pick_one(strategy.get("voice_pillars"))
    proof_point = _pick_one(strategy.get("proof_bank"))

    hook_styles = [
        "PROVOCATIVE OPENER: A bold, somewhat controversial claim about the topic. States an opinion as fact. No hedge.",
        "COUNTER-INTUITIVE FACT: Something that sounds wrong but is true. Challenges the conventional wisdom around the topic. Includes a specific number or metric.",
        "CURIOSITY GAP: States the result or end state without revealing how. The reader MUST read on to understand.",
        "VULNERABILITY OPENER: Starts with a failure, mistake, or wrong assumption the author had. Honest, specific.",
        "SPECIFIC NUMBER + OUTCOME: Leads with a concrete metric or data point that proves a non-obvious point.",
    ]

    # Pick n different styles
    selected_styles = random.sample(hook_styles, min(n, len(hook_styles)))

    hooks = []
    for style in selected_styles:
        prompt = f"""You are a ghostwriter for an indie hacker and product designer.
Write ONLY the first tweet (the hook) of a thread about: {topic}

VOICE PROFILE:
{voice}

VOICE PILLAR: {pillar or "general building"}
PROOF POINT: {proof_point or "none"}

HOOK STYLE TO USE:
{style}

RULES:
1. Under 200 characters — the hook must be punchy
2. No "Thread:" or "1/" label
3. No hashtags, no em dashes, no external URLs
4. Must make the reader desperate to read the next tweet
5. Sound exactly like the voice profile

OUTPUT: Write ONLY the hook tweet text. Nothing else."""

        raw = chat_text(prompt=prompt, max_tokens=200).strip().replace("—", "-")
        hook = _trim_to_sentence(raw, 200)
        if hook:
            hooks.append(hook)

    return hooks


def generate_thread(topic: str, num_tweets: int = 4) -> list:
    """
    Generate a thread of tweets on a topic.
    Each tweet stands alone AND connects to the next.
    """
    voice = load_voice_profile()
    config = load_config()
    strategy = config.get("content_strategy", {})
    recent_texts = _recent_post_texts(int(strategy.get("uniqueness_window", 30) or 30))
    allow_question = False
    max_attempts = int(strategy.get("max_generation_attempts", 4) or 4)

    pillar = _pick_one(strategy.get("voice_pillars"))
    angle = _pick_one(strategy.get("signature_angles"))
    proof_point = _pick_one(strategy.get("proof_bank"))
    weekly_direction = _listify(strategy.get("weekly_direction"))
    weekly_block = "\n".join([f"- {d}" for d in weekly_direction[:6]]) if weekly_direction else ""

    thread_template = {"name": "freeform", "instruction": "Freeform, still obey all rules."}
    if bool(strategy.get("thread_templates_enabled", True)) and THREAD_TEMPLATES:
        thread_template = random.choice(THREAD_TEMPLATES)

    topic_focus = topic or pillar or "general building"

    prompt_base = f"""You are a ghostwriter for an indie hacker and designer.
Write a Twitter thread of {num_tweets} tweets about: {topic_focus}

VOICE PROFILE:
{voice}

VOICE PILLAR (use exactly one):
{pillar or "general building"}

SIGNATURE ANGLE:
{angle or "none"}

PROOF POINT (must be referenced with at least one concrete detail):
{proof_point or "none"}

WEEKLY DIRECTION (optional anchors):
{weekly_block or "none"}

THREAD TEMPLATE TO FOLLOW:
{thread_template["instruction"]}

{HOOK_PATTERNS}

THREAD RULES:
1. First tweet is the hook — use one of the hook patterns above. It must stop the scroll.
2. Each tweet is under 280 characters (aim for 150-250 for educational content)
3. Each tweet stands alone AND pulls the reader to the next — no tweet is skippable
4. Thread flows naturally from start to finish — completion rate is a ranking signal
5. Last tweet is the real insight or a soft question that invites a reply ("What's your experience with this?")
6. No "Thread:" or "1/" labels — just the content
7. No hashtags
8. Use line breaks for breathing room when helpful
9. Never use em dashes
10. No external URLs in any tweet body
11. Use the proof point explicitly at least once
12. Write for bookmarks and replies — not just likes

OUTPUT FORMAT — Return ONLY a JSON array of tweet strings:
["tweet 1 text", "tweet 2 text", "tweet 3 text", "tweet 4 text"]"""

    import json
    last_reason = ""
    tweets = []
    last_cleaned = []
    for _ in range(max_attempts):
        avoid_line = f"\nAVOID THIS ISSUE:\n{last_reason}\n" if last_reason else ""
        prompt = f"{prompt_base}{avoid_line}"
        raw = chat_text(
            prompt=prompt,
            max_tokens=1000,
        ).strip()
        try:
            text = raw.replace("```json", "").replace("```", "").strip()
            tweets = json.loads(text)
        except Exception:
            lines = raw.split("\n")
            tweets = [line.strip() for line in lines if line.strip()]

        cleaned = []
        for t in tweets:
            line = _enforce_line_breaks(t.strip().replace("—", "-"))
            cleaned.append(_trim_to_sentence(line, 280))

        cleaned = cleaned[:num_tweets]
        last_cleaned = cleaned
        ok, reason = _validate_thread(
            cleaned,
            config,
            proof_point,
            allow_question,
            recent_texts,
        )
        if ok:
            return cleaned
        last_reason = reason or "failed validation"

    return last_cleaned or tweets[:num_tweets]


def generate_reply(
    tweet_text: str,
    author: str,
    author_followers: int,
    tier: str,
    extra_context: str = None
) -> str:
    """
    Generate a reply to a specific tweet.
    Tone and approach changes based on follower tier.
    """
    result = generate_reply_with_meta(
        tweet_text=tweet_text,
        author=author,
        author_followers=author_followers,
        tier=tier,
        extra_context=extra_context
    )
    return result.get("text") if result else ""


def generate_reply_with_meta(
    tweet_text: str,
    author: str,
    author_followers: int,
    tier: str,
    extra_context: str = None
) -> dict:
    voice = load_voice_profile()
    config = load_config()
    strategy = config.get("reply_strategy", {})

    tier_instruction = {
        "small": """This account has 0–1k followers. Use RELATIONSHIP mode.
Be warm, genuine, conversational.
Avoid default questions unless truly needed.
Never be generic. Read what they actually wrote.""",

        "peer": """This account has 1k–10k followers. Use PEER NETWORKING mode.
Treat them as an equal. Add a layer to their point.
Occasionally push back respectfully. Never sycophantic.""",

        "big": """This account has 10k+ followers. Use VISIBILITY mode.
You're talking to their AUDIENCE, not just them.
Sharp. Specific. One or two sentences max.
Add value that makes their followers want to click your profile."""
    }.get(tier, "Reply naturally and add value.")

    extra_section = f"\nEXTRA CONTEXT:\n{extra_context}\n" if extra_context else ""

    classification = classify_tweet(tweet_text, thread_context=extra_context, extra_context=None)
    if classification.get("should_skip"):
        return {"text": "", "meta": {"skip": True, "reason": "classifier_skip"}}

    tweet_type = classification.get("tweet_type", "opinion")

    type_to_shapes = {
        "announcement": ["reaction", "statement", "observation"],
        "opinion": ["agreement_addition", "counterpoint", "statement", "observation"],
        "question": ["direct_answer", "statement", "observation"],
        "personal_update": ["reaction", "statement", "observation", "support"],
        "win_milestone": ["statement", "observation", "support"],
        "complaint": ["support", "statement", "counterpoint"],
        "joke_meme": ["witty", "fragment", "observation"],
        "educational": ["statement", "agreement_addition", "observation"],
        "hot_take": ["counterpoint", "agreement_addition", "statement"],
        "thread": ["statement", "observation", "agreement_addition"],
        "news_reaction": ["statement", "observation", "counterpoint"],
    }

    allowed_shapes = type_to_shapes.get(tweet_type, ["statement", "observation"])

    default_distribution = {
        "statement": 0.35,
        "observation": 0.2,
        "agreement_addition": 0.15,
        "counterpoint": 0.1,
        "direct_answer": 0.1,
        "question": 0.05,
        "witty": 0.05,
        "reaction": 0.05,
        "support": 0.05,
        "fragment": 0.05,
    }
    shape_distribution = default_distribution.copy()
    for key, val in (strategy.get("shape_distribution") or {}).items():
        try:
            shape_distribution[str(key)] = float(val)
        except Exception:
            continue

    recent = recent_reply_texts(limit=strategy.get("ending_history_window", 20))
    last5_questions = question_ending_count(recent, window=strategy.get("question_end_window", 5))
    block_questions = last5_questions >= strategy.get("question_end_block_threshold", 2)

    if block_questions and "question" in allowed_shapes:
        allowed_shapes = [s for s in allowed_shapes if s != "question"]

    picked_shapes = [
        "statement",
        "observation",
        "direct_answer" if "direct_answer" in allowed_shapes else pick_shape(shape_distribution, allowed_shapes),
        pick_shape(shape_distribution, allowed_shapes),
        "witty" if "witty" in allowed_shapes else pick_shape(shape_distribution, allowed_shapes),
    ]

    prompt = f"""You are a ghostwriter for an indie hacker and designer.
Write 5 reply candidates to this tweet from @{author} ({author_followers:,} followers).

TWEET TO REPLY TO:
"{tweet_text}"

CLASSIFICATION:
Tweet type: {tweet_type}
Tone: {classification.get("tone")}
Emotional temp: {classification.get("emotional_temperature")}
Expects discussion: {classification.get("expects_discussion")}

{extra_section}

VOICE PROFILE:
{voice}

TIER INSTRUCTION:
{tier_instruction}

REPLY SHAPES (in order):
1) statement
2) observation
3) {picked_shapes[2]}
4) {picked_shapes[3]}
5) {picked_shapes[4]}

SHAPE DEFINITIONS:
- statement: declarative close, no question
- observation: one-line noticing or pattern
- agreement_addition: agree then add one new layer
- counterpoint: mild pushback with respect
- direct_answer: answer the explicit question
- reaction: short human reaction (not generic praise)
- support: encouragement or empathy
- witty: playful, punchy line
- fragment: short fragment or punchline, no question

RULES:
1. Under 240 characters
2. Sound exactly like the voice profile
3. Never start with "Great post!" or any sycophantic opener
4. Add something real — don't just agree
5. No hashtags, no emojis unless the tweet calls for it
6. Never use em dashes (—)
7. Avoid ending in a question unless the tweet explicitly invites it

OUTPUT FORMAT — Return ONLY a JSON array of strings, 5 items."""

    text = chat_text(
        prompt=prompt,
        max_tokens=400,
    ).strip()
    text = text.replace("```json", "").replace("```", "").strip()

    candidates = []
    try:
        items = json.loads(text)
        for idx, cand in enumerate(items[:5]):
            cand_text = _trim_reply(str(cand).replace("—", "-"), 240)
            candidates.append({"text": cand_text, "shape": picked_shapes[idx] if idx < len(picked_shapes) else "statement"})
    except Exception:
        for line in text.split("\n"):
            if not line.strip():
                continue
            cand_text = _trim_reply(line.strip().replace("—", "-"), 240)
            candidates.append({"text": cand_text, "shape": "statement"})

    penalties = {"question": 0.15}
    last4 = recent[:4]
    if last4 and classify_ending(last4[0]) == "question":
        penalties["question"] += 0.25
    if question_ending_count(recent, window=4) >= 2:
        penalties["question"] += 0.4

    ranked = rank_candidates(candidates, tweet_text, recent, penalties)
    if block_questions:
        ranked = [c for c in ranked if c.get("ending") != "question"] or ranked

    if not ranked:
        return {"text": "", "meta": {"skip": True, "reason": "no_candidate"}}

    best = ranked[0]
    return {
        "text": best.get("text", ""),
        "meta": {
            "tweet_type": tweet_type,
            "shape": best.get("shape"),
            "ending": best.get("ending"),
            "block_questions": block_questions,
        }
    }


def _trim_reply(text: str, max_len: int) -> str:
    return _trim_to_sentence(text, max_len)


def _trim_to_sentence(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text

    cut = text[:max_len]
    punct_idx = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
    if punct_idx >= int(max_len * 0.5):
        return cut[:punct_idx + 1].strip()

    space_idx = cut.rfind(" ")
    if space_idx >= int(max_len * 0.5):
        cut = cut[:space_idx].strip()
    else:
        cut = cut.strip()

    if cut and cut[-1] not in ".!?":
        if len(cut) + 1 <= max_len:
            cut = f"{cut}."
        elif len(cut) > 1:
            cut = f"{cut[:-1]}."

    return cut if cut else text[:max_len].strip()


def generate_dm_opener(
    username: str,
    their_tweet: str,
    your_comment: str
) -> str:
    """
    Generate a DM opener for 0-1k accounts.
    Continues the conversation from your comment — never a cold pitch.
    """
    voice = load_voice_profile()

    prompt = f"""You are a ghostwriter for an indie hacker and designer.
Write a DM opener to @{username} after commenting on their post.

YOUR COMMENT YOU LEFT: "{your_comment}"
THEIR ORIGINAL POST: "{their_tweet}"

VOICE PROFILE:
{voice}

DM RULES:
1. Continue the conversation from your comment — don't restart cold
2. Ask ONE genuine question — be actually curious
3. Never mention your product yet
4. Conversational, warm, not salesy AT ALL
5. Under 200 characters
6. Sound like a real person following up on a real conversation

OUTPUT: Write ONLY the DM text. Nothing else."""

    dm = chat_text(
        prompt=prompt,
        max_tokens=200,
    ).strip().replace("—", "-")
    return _trim_to_sentence(dm, 200)


def generate_dm_welcome(username: str) -> str:
    """
    Generate a short welcome DM for a new follower.
    """
    voice = load_voice_profile()

    prompt = f"""You are a ghostwriter for an indie hacker and designer.
Write a short, warm welcome DM to @{username} who just followed.

VOICE PROFILE:
{voice}

RULES:
1. One or two sentences max
2. No sales pitch, no links
3. No emojis unless dry and intentional
4. No em dashes (—)
5. Sound like a real person, not a template

OUTPUT: Write ONLY the DM text. Nothing else."""

    dm = chat_text(
        prompt=prompt,
        max_tokens=160,
    ).strip().replace("—", "-")
    return _trim_to_sentence(dm, 200)


def generate_dm_reply(
    username: str,
    conversation_history: list,
    their_latest_message: str,
    message_count: int
) -> str:
    """
    Continue a DM conversation.
    Naturally mentions product only after 2-3 exchanges if relevant.
    """
    voice = load_voice_profile()
    config = load_config()

    # Format conversation history
    history_text = "\n".join([
        f"{'YOU' if m['from'] == 'agent' else 'THEM'}: {m['text']}"
        for m in conversation_history[-6:]  # Last 6 messages
    ])

    product_mention = ""
    if message_count >= 2:
        product_mention = f"""
After {message_count} exchanges, it's natural to mention your product IF it's relevant.
Your product: {config['voice']['product']} — {config['voice']['product_url']}
Only mention it if it genuinely solves something they're talking about.
Don't force it."""

    prompt = f"""You are a ghostwriter for an indie hacker and designer.
Continue this DM conversation with @{username}.

CONVERSATION SO FAR:
{history_text}

THEIR LATEST MESSAGE: "{their_latest_message}"

VOICE PROFILE:
{voice}

{product_mention}

RULES:
1. Respond naturally to what they actually said
2. Keep the conversation going — ask a follow-up if natural
3. Under 200 characters
4. Sound like a real person, not a bot
5. Warm but not overly eager

OUTPUT: Write ONLY the DM reply. Nothing else."""

    dm = chat_text(
        prompt=prompt,
        max_tokens=200,
    ).strip().replace("—", "-")
    return _trim_to_sentence(dm, 200)
