"""
ai/trend_scanner.py — Trend Scanner
Scrapes Twitter's trending topics and your niche feed.
Finds what's hot RIGHT NOW and feeds it into tweet generation.
Runs once in the morning before the first tweet is generated.
"""

import asyncio
import json
import random
import uuid
from pathlib import Path
from datetime import datetime
from agent.browser import human_delay, human_scroll, human_navigate
from ai.tweet_writer import generate_tweet
from agent.logger import add_to_tweet_queue, log_action
from agent.targets import get_target_accounts
from agent.dynamic_config import load_config_with_dynamic

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
TRENDS_CACHE = Path(__file__).parent.parent / "data" / "trends_cache.json"


def load_config():
    return load_config_with_dynamic(CONFIG_PATH)


def save_trends_cache(trends: list):
    TRENDS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRENDS_CACHE, "w") as f:
        json.dump({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "trends": trends
        }, f, indent=2)


def load_trends_cache() -> list:
    """Load today's cached trends if available."""
    if not TRENDS_CACHE.exists():
        return []
    with open(TRENDS_CACHE) as f:
        data = json.load(f)
    if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
        return data.get("trends", [])
    return []


async def scrape_trending_topics(page) -> list:
    """
    Scrape trending topics from Twitter's Explore page.
    Returns a list of trending topic strings.
    """
    trends = []
    try:
        print("🔍 Scanning trending topics...")
        await human_navigate(page, "https://x.com/explore/tabs/trending")

        # Scroll a bit to load more trends
        await human_scroll(page, amount=500)
        await human_delay(1, 2)

        # Extract trending topics
        trend_selectors = [
            '[data-testid="trend"] [dir="ltr"] span',
            '[data-testid="trendItem"] span',
            'section[aria-labelledby] div[dir="ltr"] span',
        ]

        for selector in trend_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    text = await el.inner_text()
                    text = text.strip()
                    # Filter out noise — keep meaningful topics
                    if (text and len(text) > 2 and len(text) < 60
                            and not text.isdigit()
                            and "Trending" not in text
                            and "tweets" not in text.lower()
                            and "posts" not in text.lower()):
                        if text not in trends:
                            trends.append(text)
                if trends:
                    break
            except Exception:
                continue

        print(f"   Found {len(trends)} trending topics")
        return trends[:20]

    except Exception as e:
        print(f"⚠️  Trending scrape failed: {e}")
        return []


async def scrape_niche_feed(page, config: dict) -> list:
    """
    Scrape content from your target accounts' recent posts.
    Finds what's being talked about in YOUR niche specifically.
    """
    niche_topics = []
    target_accounts = get_target_accounts()
    if not target_accounts:
        target_accounts = config.get("target_accounts", [])

    # Sample a few accounts — don't visit all of them
    sample = random.sample(target_accounts, min(4, len(target_accounts)))

    print(f"📡 Scanning niche feed from {len(sample)} accounts...")

    for username in sample:
        try:
            await human_navigate(page, f"https://x.com/{username}")

            # Get their recent tweets
            tweet_els = await page.query_selector_all('[data-testid="tweetText"]')
            for el in tweet_els[:2]:
                text = await el.inner_text()
                if text and len(text) > 20:
                    niche_topics.append({
                        "author": username,
                        "text": text[:200]
                    })

            await human_delay(1, 2)

        except Exception as e:
            print(f"   ⚠️  Could not scan @{username}: {e}")
            continue

    print(f"   Found {len(niche_topics)} niche posts")
    return niche_topics


def filter_relevant_trends(trends: list, config: dict) -> list:
    """
    Filter trending topics through your niche topics.
    Keeps only trends that are relevant to indie hacking, design, AI, SaaS.
    """
    config_topics = [t.lower() for t in config.get("content_topics", [])]

    niche_keywords = [
        "ai", "saas", "startup", "design", "build", "product", "launch",
        "founder", "indie", "app", "tool", "software", "code", "ux", "ui",
        "marketing", "growth", "revenue", "user", "ship", "deploy",
        "openai", "anthropic", "claude", "gpt", "llm", "automation",
        "solopreneur", "bootstrapped", "nocode", "figma", "cursor"
    ]

    # Add config topics keywords
    for topic in config_topics:
        words = topic.lower().split()
        niche_keywords.extend(words)

    relevant = []
    for trend in trends:
        trend_lower = trend.lower()
        for keyword in niche_keywords:
            if keyword in trend_lower:
                relevant.append(trend)
                break

    return relevant


def build_trend_context(relevant_trends: list, niche_posts: list) -> str:
    """
    Build a rich trend context string to pass into tweet generation.
    """
    parts = []

    if relevant_trends:
        parts.append("TRENDING IN YOUR NICHE RIGHT NOW:")
        for t in relevant_trends[:5]:
            parts.append(f"  • {t}")

    if niche_posts:
        parts.append("\nWHAT BIG ACCOUNTS ARE TALKING ABOUT:")
        for post in niche_posts[:4]:
            parts.append(f"  @{post['author']}: \"{post['text'][:100]}...\"")

    if not parts:
        return ""

    return "\n".join(parts)


async def run_trend_scan(page) -> str:
    """
    Main function — runs the full trend scan.
    Returns a trend context string ready to pass into tweet generation.
    """
    # Check cache first — don't scan more than once per day
    cached = load_trends_cache()
    if cached:
        print("📋 Using cached trends from earlier today")
        config = load_config()
        relevant = filter_relevant_trends(cached, config)
        return build_trend_context(relevant, [])

    config = load_config()

    print("\n🌊 RUNNING TREND SCAN")
    print("=" * 40)

    # Scrape trends
    all_trends = await scrape_trending_topics(page)

    # Scrape niche feed
    niche_posts = await scrape_niche_feed(page, config)

    # Save raw trends to cache
    save_trends_cache(all_trends)

    # Filter to relevant trends
    relevant_trends = filter_relevant_trends(all_trends, config)
    print(f"\n✅ {len(relevant_trends)} relevant trends found")

    if relevant_trends:
        print("   Relevant:", ", ".join(relevant_trends[:5]))

    # Build context
    context = build_trend_context(relevant_trends, niche_posts)

    log_action(
        action_type="trend_scan",
        content=f"Found {len(relevant_trends)} relevant trends",
        metadata={
            "total_trends": len(all_trends),
            "relevant_trends": relevant_trends[:5],
            "niche_posts_scanned": len(niche_posts)
        }
    )

    print("=" * 40)
    return context


async def generate_trend_based_tweet(page) -> tuple:
    """
    Scan trends then generate a tweet that rides what's hot right now.
    Returns (tweet_id, content).
    """
    trend_context = await run_trend_scan(page)

    if trend_context:
        print("\n🤖 Generating trend-based tweet...")
        content = generate_tweet(
            tweet_type="hot_take",
            trend_context=trend_context
        )
    else:
        print("\n🤖 No relevant trends — generating from voice profile...")
        content = generate_tweet(tweet_type="auto")

    tweet_id = add_to_tweet_queue(content=content)

    print(f"📝 Tweet queued (ID: {tweet_id}): \"{content}\"")
    return tweet_id, content


async def generate_weekly_thread(page, topic: str = None) -> list:
    """
    Generate a full thread based on a trending topic or niche theme.
    Used for daily deep-dive threads.
    """
    from ai.tweet_writer import generate_thread

    if not topic:
        # Pick a topic from config
        config = load_config()
        topics = config.get("content_topics", ["indie hacking"])
        topic = random.choice(topics)

    print(f"\n🧵 Generating thread about: {topic}")
    tweets = generate_thread(topic=topic, num_tweets=5)

    # Add thread to queue as separate tweets
    tweet_ids = []
    thread_id = uuid.uuid4().hex
    for i, tweet in enumerate(tweets):
        tweet_id = add_to_tweet_queue(
            content=tweet,
            scheduled_for=f"Thread part {i+1}/{len(tweets)}",
            thread_id=thread_id,
            thread_index=i + 1
        )
        tweet_ids.append(tweet_id)
        print(f"   Part {i+1}: \"{tweet[:60]}...\"")

    print(f"✅ Thread queued — {len(tweets)} tweets pending approval")
    return tweet_ids
