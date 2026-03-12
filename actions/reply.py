"""
actions/reply.py — Tiered reply system
Monitors target accounts and replies based on follower count tier.
This is your #1 growth lever — early replies on big accounts = massive reach.
"""

import asyncio
import json
import os
import random
import sqlite3
import urllib.parse
from datetime import datetime
from pathlib import Path
from agent.browser import human_delay, human_type, human_click, human_scroll
from agent.logger import log_action, is_limit_reached, get_daily_count, DB_PATH
from agent.targets import get_target_accounts, maybe_auto_add_target, remove_target
from agent.hashtags import load_hashtags
from ai.tweet_writer import generate_reply_with_meta
from ai.vision import describe_images
from ai.relevance import text_to_embedding, cosine_similarity, topic_signature
from agent.pacing import cooldown_remaining_seconds, record_rate_limit, sleep_with_pacing
from agent.status_overlay import set_status
from agent.mentions import apply_tool_mentions, type_with_mentions
from actions.like import like_tweet, already_liked
from agent.humanize import maybe_micro_break
from agent import quality
from dotenv import load_dotenv
from agent.dynamic_config import load_config_with_dynamic

load_dotenv()

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
SELF_USERNAME = os.getenv("TWITTER_USERNAME", "").strip().lstrip("@").lower()
TOPIC_HISTORY_PATH = Path(__file__).parent.parent / "data" / "topic_history.json"


def load_config():
    return load_config_with_dynamic(CONFIG_PATH)


def _resolve_media_path(media_path: str) -> str:
    if not media_path:
        return ""
    media = Path(media_path)
    if media.is_absolute():
        return str(media)
    return str((Path(__file__).parent.parent / media).resolve())


async def _attach_media(page, media_path: str) -> bool:
    if not media_path:
        return False
    resolved = _resolve_media_path(media_path)
    if not Path(resolved).exists():
        print(f"⚠️  Media file not found: {resolved}")
        return False

    input_selectors = [
        'input[type="file"]',
        'input[data-testid="fileInput"]',
        'input[accept*="image"]',
        'input[accept*="video"]',
    ]
    file_input = None
    for selector in input_selectors:
        try:
            file_input = await page.query_selector(selector)
            if file_input:
                break
        except Exception:
            continue

    if not file_input:
        print("⚠️  Could not find media upload input")
        return False

    await file_input.set_input_files(resolved)
    await human_delay(1.2, 2.2)
    return True


async def _wait_for_post_enabled(page, timeout_ms: int = 45000) -> None:
    post_selectors = [
        '[data-testid="tweetButtonInline"]',
        '[data-testid="tweetButton"]',
    ]
    for selector in post_selectors:
        try:
            await page.wait_for_function(
                """(sel) => {
                    const btn = document.querySelector(sel);
                    if (!btn) return false;
                    const ariaDisabled = btn.getAttribute("aria-disabled");
                    return !btn.disabled && ariaDisabled !== "true";
                }""",
                selector,
                timeout=timeout_ms,
            )
            return
        except Exception:
            continue


def get_tier(followers: int, config: dict) -> str:
    """Determine which tier an account falls into."""
    tiers = config["tiers"]
    if followers <= tiers["small"]["max_followers"]:
        return "small"
    elif followers <= tiers["peer"]["max_followers"]:
        return "peer"
    else:
        return "big"


def already_replied_to(tweet_url: str) -> bool:
    """Check if we've already replied to this specific tweet."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id FROM actions
        WHERE action_type = 'reply'
        AND metadata LIKE ?
        LIMIT 1
    """, (f'%{tweet_url}%',))
    row = c.fetchone()
    conn.close()
    return row is not None


async def _profile_missing(page) -> bool:
    checks = [
        "This account doesn’t exist",
        "This account doesn't exist",
        "This account is suspended",
        "Account suspended",
        "User not found",
    ]
    for text in checks:
        try:
            el = await page.query_selector(f'text="{text}"')
            if el:
                return True
        except Exception:
            continue
    return False


async def get_follower_count(page, username: str):
    """Get follower count for a Twitter user."""
    try:
        await page.goto(f"https://x.com/{username}", wait_until="domcontentloaded")
        await human_delay(2, 3)

        if await _profile_missing(page):
            print(f"⚠️  @{username} does not exist or is unavailable")
            return None

        # Try to find follower count
        selectors = [
            f'[href*="/{username}/followers" i] span span',
            '[data-testid="UserProfileHeader_Items"] a[href*="/followers"] span',
        ]

        try:
            el = await page.wait_for_selector(", ".join(selectors), timeout=8000)
            if el:
                text = await el.inner_text()
                return _parse_follower_count(text)
        except Exception:
            pass

        return 0
    except Exception as e:
        print(f"⚠️  Could not get follower count for @{username}: {e}")
        return 0


async def get_profile_snapshot(page, username: str, count: int = 3, allow_self: bool = False):
    """Load a profile once and return follower count + recent tweets."""
    try:
        await page.goto(f"https://x.com/{username}", wait_until="domcontentloaded")
        await human_delay(2, 3)

        if await _profile_missing(page):
            print(f"⚠️  @{username} does not exist or is unavailable")
            return None, []

        followers = 0
        selectors = [
            f'[href*="/{username}/followers" i] span span',
            '[data-testid="UserProfileHeader_Items"] a[href*="/followers"] span',
        ]
        try:
            el = await page.wait_for_selector(", ".join(selectors), timeout=8000)
            if el:
                text = await el.inner_text()
                followers = _parse_follower_count(text)
        except Exception:
            pass

        tweets = []
        articles = await page.query_selector_all('[data-testid="tweet"]')
        for article in articles:
            parsed = await _parse_tweet_article(article, allow_self=allow_self)
            if parsed and parsed.get("text") and parsed.get("url"):
                tweets.append(parsed)
            if len(tweets) >= count:
                break

        if count > 1:
            await human_scroll(page, amount=random.randint(200, 500))
            await human_delay(0.6, 1.2)

        return followers, tweets
    except Exception as e:
        print(f"⚠️  Could not load profile snapshot for @{username}: {e}")
        return 0, []


def _reading_delay_seconds(text: str) -> float:
    words = len((text or "").split())
    if words <= 0:
        return 0.0
    wpm = random.randint(180, 260)
    seconds = words / (wpm / 60.0)
    seconds = max(1.5, min(seconds, 12.0))
    return seconds * random.uniform(0.8, 1.2)


async def _simulate_reading(text: str) -> None:
    seconds = _reading_delay_seconds(text)
    if seconds > 0:
        await asyncio.sleep(seconds)


def _parse_follower_count(text: str) -> int:
    """Parse '12.5K' or '1,234' into an integer."""
    text = text.strip().replace(",", "")
    if "K" in text.upper():
        return int(float(text.upper().replace("K", "")) * 1000)
    elif "M" in text.upper():
        return int(float(text.upper().replace("M", "")) * 1000000)
    try:
        return int(text)
    except Exception:
        return 0


def _relevance_keywords(config: dict) -> list:
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


def _is_relevant(text: str, keywords: list) -> bool:
    if not keywords:
        return True
    text_lower = (text or "").lower()
    return any(k in text_lower for k in keywords)


def _build_relevance_profile(config: dict) -> str:
    voice = config.get("voice", {})
    parts = []
    for key in ["niche", "product", "personality"]:
        if voice.get(key):
            parts.append(str(voice.get(key)))
    parts.extend(config.get("content_topics", []))
    return " | ".join(parts)


def _embedding_score(text: str, profile_text: str) -> float:
    if not text or not profile_text:
        return 0.0
    return cosine_similarity(
        text_to_embedding(text),
        text_to_embedding(profile_text)
    )


def _should_flag_dm(source: str, config: dict) -> bool:
    discovery = config.get("discovery", {})
    if source.startswith("hashtag:"):
        return discovery.get("dm_from_hashtags", False)
    if source == "home_feed":
        return discovery.get("dm_from_home_feed", False)
    return True


def _truncate(text: str, max_len: int) -> str:
    if not text:
        return ""
    return text if len(text) <= max_len else text[:max_len].rstrip() + "..."


async def _tweet_has_video(tweet_el) -> bool:
    selectors = [
        "video",
        '[data-testid="videoComponent"]',
        '[data-testid="videoPlayer"]',
        '[aria-label*="Video"]',
    ]
    for selector in selectors:
        try:
            if await tweet_el.query_selector(selector):
                return True
        except Exception:
            continue
    return False


def _parse_engagement_label(label: str) -> int:
    if not label:
        return 0
    parts = label.replace(",", "").split()
    for part in parts:
        if part.replace(".", "").isdigit():
            try:
                return int(float(part))
            except Exception:
                continue
        if part.upper().endswith("K") and part[:-1].replace(".", "").isdigit():
            return int(float(part[:-1]) * 1000)
        if part.upper().endswith("M") and part[:-1].replace(".", "").isdigit():
            return int(float(part[:-1]) * 1000000)
    return 0


async def _get_engagement_counts(tweet_el) -> dict:
    counts = {"replies": 0, "retweets": 0, "likes": 0}
    selectors = {
        "replies": '[data-testid="reply"]',
        "retweets": '[data-testid="retweet"]',
        "likes": '[data-testid="like"]',
    }
    for key, selector in selectors.items():
        try:
            btn = await tweet_el.query_selector(selector)
            if not btn:
                continue
            label = await btn.get_attribute("aria-label")
            counts[key] = _parse_engagement_label(label)
        except Exception:
            continue
    return counts


def _is_low_engagement(tweet: dict, config: dict) -> bool:
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


def _is_bait(text: str, config: dict) -> bool:
    lower = (text or "").lower()
    for phrase in config.get("discovery", {}).get("skip_bait_phrases", []):
        if phrase and phrase in lower:
            return True
    return False


def _is_english(text: str) -> bool:
    if not text:
        return False
    if len(text) < 20:
        return True
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    ascii_letters = [c for c in letters if ord(c) < 128]
    if len(ascii_letters) / len(letters) < 0.7:
        return False
    lower = f" {text.lower()} "
    common = [" the ", " and ", " to ", " of ", " in ", " for ", " with ", " on "]
    hits = sum(1 for w in common if w in lower)
    return hits >= 1


def _load_topic_history(config: dict) -> list:
    window_hours = config.get("discovery", {}).get("repeat_topic_window_hours", 48)
    cutoff = datetime.now().timestamp() - (window_hours * 3600)
    if TOPIC_HISTORY_PATH.exists():
        try:
            with open(TOPIC_HISTORY_PATH) as f:
                items = json.load(f)
        except Exception:
            items = []
    else:
        items = []

    cleaned = [item for item in items if item.get("ts", 0) >= cutoff]
    if cleaned != items:
        _save_topic_history(cleaned)
    return cleaned


def _save_topic_history(items: list) -> None:
    TOPIC_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOPIC_HISTORY_PATH, "w") as f:
        json.dump(items, f, indent=2)


def _is_repeated_topic(text: str, config: dict) -> bool:
    signature = topic_signature(text)
    if not signature:
        return False
    history = _load_topic_history(config)
    repeats = [h for h in history if h.get("sig") == signature]
    max_repeats = config.get("discovery", {}).get("max_topic_repeats", 2)
    return len(repeats) >= max_repeats


def _record_topic(text: str, config: dict) -> None:
    signature = topic_signature(text)
    if not signature:
        return
    history = _load_topic_history(config)
    history.append({"sig": signature, "ts": datetime.now().timestamp()})
    _save_topic_history(history)


async def _maybe_like_tweet(page, tweet_url: str, author: str, text: str, config: dict, source: str) -> None:
    if not tweet_url:
        return
    if is_limit_reached("like", config["engagement"]["daily_likes"]):
        return
    if already_liked(tweet_url):
        return
    success = await like_tweet(page, tweet_url)
    if success:
        log_action(
            action_type="like",
            target_user=author,
            content=(text or "")[:100],
            success=True,
            metadata={"tweet_url": tweet_url, "source": source}
        )
async def _extract_media_context(tweet_el) -> str:
    contexts = []
    try:
        images = await tweet_el.query_selector_all("img")
        for img in images:
            alt = await img.get_attribute("alt") or await img.get_attribute("aria-label")
            if not alt:
                continue
            alt_clean = alt.strip()
            if not alt_clean:
                continue
            lower = alt_clean.lower()
            if lower in ["image", "photo", "graphic"]:
                continue
            contexts.append(alt_clean)
    except Exception:
        pass

    if not contexts:
        return ""

    if len(contexts) > 3:
        contexts = contexts[:3]

    return " | ".join(contexts)


async def _extract_image_sources(tweet_el) -> list:
    sources = []
    try:
        images = await tweet_el.query_selector_all("img")
        for img in images:
            src = await img.get_attribute("src")
            if not src:
                continue
            if "profile_images" in src or "emoji" in src:
                continue
            if src not in sources:
                sources.append(src)
    except Exception:
        pass
    return sources


async def _parse_tweet_article(article, allow_self: bool = False) -> dict:
    text_nodes = await article.query_selector_all('[data-testid="tweetText"]')
    text_parts = []
    for node in text_nodes:
        try:
            text = await node.inner_text()
        except Exception:
            text = ""
        if text:
            text_parts.append(text.strip())

    text = "\n\n".join(text_parts).strip()
    if not text:
        return {}

    time_el = await article.query_selector("time")
    link = ""
    if time_el:
        parent_a = await time_el.evaluate_handle("el => el.closest('a')")
        href = await parent_a.get_attribute("href")
        if href:
            link = f"https://twitter.com{href}"

    author = ""
    try:
        author_el = await article.query_selector('[data-testid="User-Name"] a')
        if author_el:
            href = await author_el.get_attribute("href")
            author = href.strip("/") if href else ""
    except Exception:
        author = ""

    if not allow_self and author and author.lower() == SELF_USERNAME:
        return {}

    has_video = await _tweet_has_video(article)
    image_sources = await _extract_image_sources(article)
    engagement = await _get_engagement_counts(article)

    media_context = await _extract_media_context(article)
    extra_context = []
    if media_context:
        extra_context.append(f"Image description: {media_context}")
    if len(text_nodes) > 1:
        extra_context.append("Multiple parts visible (thread or quoted tweet).")

    return {
        "text": text,
        "url": link,
        "author": author,
        "extra_context": "\n".join(extra_context).strip() if extra_context else None,
        "has_video": has_video,
        "image_sources": image_sources,
        "engagement": engagement,
    }


async def _collect_tweets_from_page(page, max_tweets: int = 30, scrolls: int = 2) -> list:
    tweets = []
    seen = set()

    max_scrolls = max(1, int(scrolls))
    total_scrolls = random.randint(1, max_scrolls)
    for _ in range(total_scrolls + 1):
        articles = await page.query_selector_all('[data-testid="tweet"]')
        for article in articles:
            parsed = await _parse_tweet_article(article, allow_self=False)
            if not parsed:
                continue
            if not parsed.get("url") or not parsed.get("author"):
                continue
            if parsed["url"] in seen:
                continue
            seen.add(parsed["url"])
            tweets.append(parsed)
            if len(tweets) >= max_tweets:
                return tweets
        await human_scroll(page, amount=random.randint(600, 1000))
        await human_delay(1.5, 3)

    return tweets


async def _search_hashtag_tweets(page, hashtag: str, max_tweets: int = 40, top_ratio: float = 0.4) -> list:
    tag = hashtag.strip()
    if not tag:
        return []
    if not tag.startswith("#"):
        tag = f"#{tag}"

    top_ratio = min(max(top_ratio, 0.0), 1.0)
    top_count = int(round(max_tweets * top_ratio))
    latest_count = max_tweets - top_count
    if max_tweets > 0 and top_ratio > 0 and top_count == 0:
        top_count = 1
        latest_count = max_tweets - top_count
    if max_tweets > 0 and top_ratio < 1 and latest_count == 0:
        latest_count = 1
        top_count = max_tweets - latest_count

    collected = []
    seen = set()

    if top_count > 0:
        query = urllib.parse.quote(tag)
        url = f"https://x.com/search?q={query}&src=typed_query"
        await page.goto(url, wait_until="domcontentloaded")
        await human_delay(2.5, 4.5)
        top_tweets = await _collect_tweets_from_page(page, max_tweets=top_count, scrolls=2)
        for tweet in top_tweets:
            if tweet.get("url") and tweet["url"] not in seen:
                seen.add(tweet["url"])
                collected.append(tweet)

    if latest_count > 0:
        query = urllib.parse.quote(tag)
        url = f"https://x.com/search?q={query}&src=typed_query&f=live"
        await page.goto(url, wait_until="domcontentloaded")
        await human_delay(2.5, 4.5)
        latest_tweets = await _collect_tweets_from_page(page, max_tweets=latest_count, scrolls=2)
        for tweet in latest_tweets:
            if tweet.get("url") and tweet["url"] not in seen:
                seen.add(tweet["url"])
                collected.append(tweet)

    return collected


async def _home_feed_tweets(page, max_tweets: int = 50) -> list:
    await page.goto("https://x.com/home", wait_until="domcontentloaded")
    await human_delay(2, 3)
    return await _collect_tweets_from_page(page, max_tweets=max_tweets, scrolls=2)


async def _get_full_thread_context(page, tweet_url: str, author: str, config: dict) -> dict:
    await page.goto(tweet_url, wait_until="domcontentloaded")
    await human_delay(2, 4)

    expand_selectors = [
        'div[role="button"]:has-text("Show more")',
        'div[role="button"]:has-text("Show replies")',
        'div[role="button"]:has-text("Show more replies")',
        'div[role="button"]:has-text("Show this thread")',
        'a:has-text("Show this thread")',
        'div[role="button"]:has-text("Show")',
        '[data-testid="showMoreText"]',
    ]

    for _ in range(4):
        clicked = False
        for selector in expand_selectors:
            try:
                buttons = await page.query_selector_all(selector)
                for btn in buttons:
                    await human_click(page, btn)
                    await human_delay(0.6, 1.2)
                    clicked = True
            except Exception:
                continue
        if not clicked:
            break

    collected = []
    image_sources = []
    has_video = False
    max_parts = 12

    max_scrolls = random.randint(3, 5)
    for _ in range(max_scrolls):
        articles = await page.query_selector_all('[data-testid="tweet"]')

        for article in articles:
            parsed = await _parse_tweet_article(article, allow_self=True)
            if not parsed:
                continue
            if parsed.get("author", "").lower() != (author or "").lower():
                continue
            if parsed.get("has_video"):
                has_video = True
            if parsed.get("image_sources"):
                image_sources.extend(parsed["image_sources"])
            if parsed.get("text") and parsed["text"] not in collected:
                collected.append(parsed["text"])
            if len(collected) >= max_parts:
                break

        if len(collected) >= max_parts:
            break

        await human_scroll(page, amount=random.randint(600, 1000))
        await human_delay(1.2, 2.4)

    unique_sources = []
    for src in image_sources:
        if src not in unique_sources:
            unique_sources.append(src)

    vision_cfg = config.get("vision", {})
    vision_context = None
    if vision_cfg.get("enabled", False) and unique_sources:
        vision_context = describe_images(
            unique_sources,
            model=vision_cfg.get("model"),
            max_images=vision_cfg.get("max_images_per_tweet", 2),
            max_bytes=vision_cfg.get("max_image_bytes", 2000000)
        )

    thread_text = "\n\n".join(collected).strip()
    return {
        "thread_text": thread_text,
        "has_video": has_video,
        "vision_context": vision_context,
        "thread_parts": len(collected),
    }


async def get_latest_tweets(page, username: str, count: int = 3, allow_self: bool = False) -> list:
    """Get the most recent tweets from a user's profile."""
    tweets = []
    try:
        await page.goto(f"https://x.com/{username}", wait_until="domcontentloaded")
        await human_delay(2, 4)

        # Find tweet articles
        tweet_articles = await page.query_selector_all('[data-testid="tweet"]')

        for article in tweet_articles:
            parsed = await _parse_tweet_article(article, allow_self=allow_self)
            if parsed and parsed.get("text") and parsed.get("url"):
                tweets.append(parsed)
            if len(tweets) >= count:
                break

        return tweets

    except Exception as e:
        print(f"⚠️  Could not get tweets for @{username}: {e}")
        return []


async def reply_to_tweet(page, tweet_url: str, reply_text: str, media_path: str = None, media_type: str = None) -> bool:
    """Navigate to a tweet and post a reply."""
    try:
        config = load_config()
        reply_text = apply_tool_mentions(reply_text, config)

        await page.goto(tweet_url, wait_until="domcontentloaded")
        await human_delay(2, 4)

        # Find the reply box
        # Twitter's UI changes frequently. Include fallbacks for both the
        # inline timeline reply and the modal reply textareas.
        reply_selectors = [
            '[data-testid="tweetTextarea_0"]',
            '[data-testid="tweetTextarea_0_label"]',
            '[aria-label="Post text"]',
            '[aria-label="Tweet text"]',
            '.public-DraftEditor-content',
        ]

        reply_box = None
        for selector in reply_selectors:
            try:
                # Sometimes need to click Reply button first
                reply_btn = await page.query_selector('[data-testid="reply"]')
                if reply_btn:
                    await human_click(page, reply_btn)
                    await human_delay(1, 2)

                reply_box = await page.wait_for_selector(selector, timeout=5000)
                if reply_box:
                    break
            except Exception:
                continue

        if not reply_box:
            return False

        await human_click(page, reply_box)
        await human_delay(0.5, 1)
        await type_with_mentions(page, reply_box, reply_text)
        await human_delay(1, 2.5)

        if media_path:
            attached = await _attach_media(page, media_path)
            if attached:
                await _wait_for_post_enabled(page)

        # Post the reply
        post_selectors = [
            '[data-testid="tweetButtonInline"]',
            '[data-testid="tweetButton"]',
        ]

        try:
            btn = await page.wait_for_selector(", ".join(post_selectors), timeout=8000)
            if btn:
                await human_delay(0.5, 1.2)
                await human_click(page, btn)
                await human_delay(2, 3)
                # Check for rate limit / error toast
                try:
                    toast = await page.query_selector('[data-testid="toast"]')
                    if toast:
                        text = (await toast.inner_text()).lower()
                        if "rate limit" in text or "too many" in text or "try again" in text:
                            config = load_config()
                            cooldown = config.get("safety", {}).get("rate_limit_cooldown_minutes", 45)
                            record_rate_limit("reply", cooldown, reason=text[:120])
                            return False
                except Exception:
                    pass
                return True
        except Exception:
            pass

        return False

    except Exception as e:
        print(f"❌ Reply error: {e}")
        return False


async def _reply_to_candidates(page, candidates: list, config: dict, max_replies: int, source: str) -> int:
    replies = 0
    keywords = _relevance_keywords(config)
    profile_text = _build_relevance_profile(config)
    discovery = config.get("discovery", {})
    use_embeddings = discovery.get("use_embeddings", False)
    embedding_threshold = discovery.get("embedding_threshold", 0.0)
    require_keyword = discovery.get("require_keyword_match", False)

    cooldown = cooldown_remaining_seconds()
    if cooldown > 0:
        print(f"⏸  Reply cooldown active ({cooldown}s). Waiting...")
        await asyncio.sleep(cooldown)
        return replies
    random.shuffle(candidates)

    for tweet in candidates:
        if replies >= max_replies:
            break

        if is_limit_reached("reply", config["engagement"]["daily_replies"]):
            break

        if not tweet.get("url") or not tweet.get("author"):
            continue

        if already_replied_to(tweet["url"]):
            continue

        if tweet.get("has_video"):
            continue

        relevance_text = f"{tweet.get('text', '')} {tweet.get('extra_context') or ''}"
        if _is_low_engagement(tweet, config):
            continue
        if _is_bait(relevance_text, config):
            continue
        if not _is_english(tweet.get("text", "")):
            continue

        author = tweet["author"]
        await set_status(f"Reply candidate @{author} ({source})")
        print(f"   ↳ Considering @{author} from {source}")

        followers = await get_follower_count(page, author)
        if followers is None:
            followers = 0
        tier = get_tier(followers, config)

        thread_context = await _get_full_thread_context(page, tweet["url"], author, config)
        if thread_context.get("has_video"):
            continue

        thread_text = thread_context.get("thread_text") or tweet.get("text", "")
        thread_text = _truncate(thread_text, 1200)

        if not _is_english(thread_text):
            continue
        if _is_repeated_topic(thread_text, config):
            continue

        topic_ratio = quality.thread_topic_ratio(thread_text, config, profile_text, keywords)
        if topic_ratio < discovery.get("thread_topic_min_ratio", 0.0):
            continue
        if quality.text_quality_score(thread_text, config) < discovery.get("thread_quality_min_score", 0.0):
            continue

        keyword_ok = _is_relevant(thread_text, keywords)
        if require_keyword and not keyword_ok:
            continue

        if use_embeddings:
            score = _embedding_score(thread_text, profile_text)
            if score < embedding_threshold:
                continue

        passes_quality, _ = quality.candidate_passes(thread_text, tweet, config, profile_text, keywords)
        if not passes_quality:
            continue

        await _simulate_reading(thread_text)

        extra_context_parts = []
        if tweet.get("extra_context"):
            extra_context_parts.append(tweet["extra_context"])
        if thread_context.get("vision_context"):
            extra_context_parts.append(f"Image context: {thread_context['vision_context']}")
        if len(thread_text) > len(tweet.get("text", "")):
            extra_context_parts.append("Full thread read.")

        reply_payload = generate_reply_with_meta(
            tweet_text=thread_text,
            author=author,
            author_followers=followers,
            tier=tier,
            extra_context="\n".join(extra_context_parts) if extra_context_parts else None
        )
        reply_text = reply_payload.get("text") if reply_payload else ""
        if not reply_text:
            continue
        print(f"   ↳ Reply: \"{reply_text}\"")

        await set_status(f"Replying to @{author}")
        success = await reply_to_tweet(page, tweet["url"], reply_text)

        log_action(
            action_type="reply",
            target_user=author,
            target_user_followers=followers,
            tier=tier,
            content=reply_text,
            success=success,
            metadata={
                "tweet_url": tweet["url"],
                "source": source,
                **(reply_payload.get("meta") or {})
            }
        )

        if success:
            replies += 1
            print(f"   ✅ Reply posted!")
            maybe_auto_add_target(author, followers, source=source)
            if tier == "small" and _should_flag_dm(source, config):
                _flag_for_dm_followup(author, followers, thread_text, reply_text)
            _record_topic(thread_text, config)
            await _maybe_like_tweet(page, tweet["url"], author, tweet.get("text", ""), config, source="reply_followup")
            await maybe_micro_break(label="Short break (after reply)")

        delay = random.uniform(
            config["engagement"]["min_delay_seconds"],
            config["engagement"]["max_delay_seconds"]
        )
        print(f"   ⏳ Waiting {delay:.0f}s before next action...")
        await sleep_with_pacing(delay, config, "reply")

    return replies


async def run_reply_session(
    page,
    max_replies: int = 10,
    target_limit: int = None,
    max_hashtag_replies_override: int = None,
    max_home_replies_override: int = None,
):
    """
    Main reply session — goes through target accounts and replies.
    Respects daily limits and tier-appropriate behavior.
    """
    config = load_config()
    discovery = config.get("discovery", {})
    profile_text = _build_relevance_profile(config)
    keywords = _relevance_keywords(config)
    use_embeddings = discovery.get("use_embeddings", False)
    embedding_threshold = discovery.get("embedding_threshold", 0.0)
    require_keyword = discovery.get("require_keyword_match", False)

    cooldown = cooldown_remaining_seconds()
    if cooldown > 0:
        print(f"⏸  Reply cooldown active ({cooldown}s). Waiting...")
        await asyncio.sleep(cooldown)
        return

    if is_limit_reached("reply", config["engagement"]["daily_replies"]):
        print("⚠️  Daily reply limit reached")
        return

    target_accounts = get_target_accounts()
    if not target_accounts:
        target_accounts = config.get("target_accounts", [])
    random.shuffle(target_accounts)  # Vary the order each time

    replies_this_session = 0
    target_sessions_per_day = discovery.get("target_profile_sessions_per_day", 2)
    if target_limit is not None and target_limit <= 0:
        target_accounts = []
    elif target_sessions_per_day is not None:
        if get_daily_count("target_profile_session") >= target_sessions_per_day:
            target_accounts = []
    if target_accounts:
        log_action(
            action_type="target_profile_session",
            content="Scanning target profiles",
            metadata={"limit": target_sessions_per_day}
        )

    for username in target_accounts:
        if replies_this_session >= max_replies:
            break
        if target_limit is not None and replies_this_session >= target_limit:
            break

        if is_limit_reached("reply", config["engagement"]["daily_replies"]):
            break

        print(f"\n👀 Checking @{username}...")
        await set_status(f"Checking @{username}")

        # Get their follower count to determine tier
        followers, tweets = await get_profile_snapshot(page, username, count=2)
        if followers is None:
            removed = remove_target(username)
            if removed:
                log_action(
                    action_type="target_removed",
                    target_user=username,
                    success=True,
                    metadata={"reason": "not_found"}
                )
                print(f"   🗑️ Removed @{username} (not found)")
            continue
        tier = get_tier(followers, config)

        print(f"   Followers: {followers:,} → Tier: {tier}")

        # Get their recent tweets
        if not tweets:
            tweets = await get_latest_tweets(page, username, count=2)

        for tweet in tweets:
            if already_replied_to(tweet["url"]):
                print(f"   ↳ Already replied to this tweet, skipping")
                continue

            if tweet.get("has_video"):
                continue
            if _is_low_engagement(tweet, config):
                continue
            if _is_bait(tweet.get("text", ""), config):
                continue
            if not _is_english(tweet.get("text", "")):
                continue

            thread_context = await _get_full_thread_context(page, tweet["url"], username, config)
            if thread_context.get("has_video"):
                continue

            thread_text = thread_context.get("thread_text") or tweet.get("text", "")
            thread_text = _truncate(thread_text, 1200)

            if not _is_english(thread_text):
                continue
            if _is_repeated_topic(thread_text, config):
                continue

            topic_ratio = quality.thread_topic_ratio(thread_text, config, profile_text, keywords)
            if topic_ratio < discovery.get("thread_topic_min_ratio", 0.0):
                continue
            if quality.text_quality_score(thread_text, config) < discovery.get("thread_quality_min_score", 0.0):
                continue

            keyword_ok = _is_relevant(thread_text, keywords)
            if require_keyword and not keyword_ok:
                continue

            if use_embeddings:
                score = _embedding_score(thread_text, profile_text)
                if score < embedding_threshold:
                    continue

            passes_quality, _ = quality.candidate_passes(thread_text, tweet, config, profile_text, keywords)
            if not passes_quality:
                continue

            await _simulate_reading(thread_text)

            extra_context_parts = []
            if tweet.get("extra_context"):
                extra_context_parts.append(tweet["extra_context"])
            if thread_context.get("vision_context"):
                extra_context_parts.append(f"Image context: {thread_context['vision_context']}")
            if len(thread_text) > len(tweet.get("text", "")):
                extra_context_parts.append("Full thread read.")

            # Generate a reply in the right tone for this tier
            print(f"   ↳ Generating {tier} reply...")
            reply_payload = generate_reply_with_meta(
                tweet_text=thread_text,
                author=username,
                author_followers=followers,
                tier=tier,
                extra_context="\n".join(extra_context_parts) if extra_context_parts else None
            )

            reply_text = reply_payload.get("text") if reply_payload else ""
            if not reply_text:
                continue
            print(f"   ↳ Reply: \"{reply_text}\"")

            # Post it
            await set_status(f"Replying to @{username}")
            success = await reply_to_tweet(page, tweet["url"], reply_text)

            log_action(
                action_type="reply",
                target_user=username,
                target_user_followers=followers,
                tier=tier,
                content=reply_text,
                success=success,
                metadata={
                    "tweet_url": tweet["url"],
                    "source": "target_list",
                    **(reply_payload.get("meta") or {})
                }
            )

            if success:
                replies_this_session += 1
                print(f"   ✅ Reply posted!")

                # If small tier, flag for potential DM follow-up
                if tier == "small" and _should_flag_dm("target_list", config):
                    _flag_for_dm_followup(username, followers, tweet["text"], reply_text)

                _record_topic(thread_text, config)
                await _maybe_like_tweet(page, tweet["url"], username, tweet.get("text", ""), config, source="reply_followup")
                await maybe_micro_break(label="Short break (after reply)")

            # Human-like pause between replies
            delay = random.uniform(
                config["engagement"]["min_delay_seconds"],
                config["engagement"]["max_delay_seconds"]
            )
            print(f"   ⏳ Waiting {delay:.0f}s before next action...")
            await sleep_with_pacing(delay, config, "reply")

            break  # One reply per account per session

        # Pause between accounts
        await human_delay(5, 15)

    discovery = config.get("discovery", {})
    remaining = max(0, max_replies - replies_this_session)

    if remaining > 0 and discovery.get("reply_from_hashtags", False):
        hashtags = load_hashtags()
        random.shuffle(hashtags)
        max_hashtag_cap = discovery.get("max_hashtag_replies_per_session", 0)
        if max_hashtag_replies_override is not None:
            max_hashtag_cap = max_hashtag_replies_override
        max_hashtag = min(max_hashtag_cap, remaining)
        scanned_limit = discovery.get("max_hashtag_tweets_scanned", 40)
        hashtag_replies = 0

        for tag in hashtags:
            if hashtag_replies >= max_hashtag:
                break
            print(f"\n🔎 Hashtag scan: #{tag}")
            top_ratio = discovery.get("hashtag_top_ratio", 0.4)
            tweets = await _search_hashtag_tweets(page, tag, max_tweets=scanned_limit, top_ratio=top_ratio)
            added = await _reply_to_candidates(
                page,
                tweets,
                config,
                max_hashtag - hashtag_replies,
                source=f"hashtag:{tag}"
            )
            hashtag_replies += added
            replies_this_session += added

        remaining = max(0, max_replies - replies_this_session)

    if remaining > 0 and discovery.get("reply_from_home_feed", False):
        max_home_cap = discovery.get("max_home_replies_per_session", 0)
        if max_home_replies_override is not None:
            max_home_cap = max_home_replies_override
        max_home = min(max_home_cap, remaining)
        scanned_limit = discovery.get("max_home_tweets_scanned", 50)
        print("\n🏠 Home feed scan for replies")
        tweets = await _home_feed_tweets(page, max_tweets=scanned_limit)
        added = await _reply_to_candidates(
            page,
            tweets,
            config,
            max_home,
            source="home_feed"
        )
        replies_this_session += added

    print(f"\n✅ Reply session done — {replies_this_session} replies posted")


def _flag_for_dm_followup(username: str, followers: int, their_tweet: str, your_reply: str):
    """Flag a small account for potential DM follow-up."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Check if already in DM pipeline
    c.execute("""
        SELECT id FROM dm_conversations WHERE username = ?
    """, (username,))
    existing = c.fetchone()

    if not existing:
        import json
        from datetime import datetime
        c.execute("""
            INSERT INTO dm_conversations
            (username, followers, started_at, status, conversation_json)
            VALUES (?, ?, ?, 'flagged', ?)
        """, (
            username,
            followers,
            datetime.now().isoformat(),
            json.dumps({"their_tweet": their_tweet, "your_reply": your_reply})
        ))
        conn.commit()
        print(f"   📌 @{username} flagged for potential DM follow-up")

    conn.close()
