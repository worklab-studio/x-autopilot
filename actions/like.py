"""
actions/like.py — Strategic liking
Likes tweets from target accounts and niche hashtags.
Warms up accounts before following or replying.
"""

import asyncio
import random
import os
from pathlib import Path
from agent.browser import human_delay, human_click, human_scroll
from agent.logger import log_action, is_limit_reached, DB_PATH
from agent import quality
import sqlite3
from agent.status_overlay import set_status
from agent.pacing import record_rate_limit
from agent.humanize import maybe_micro_break
from agent.dynamic_config import load_config_with_dynamic

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config():
    return load_config_with_dynamic(CONFIG_PATH)


def already_liked(tweet_url: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id FROM actions
        WHERE action_type = 'like' AND metadata LIKE ? LIMIT 1
    """, (f'%{tweet_url}%',))
    row = c.fetchone()
    conn.close()
    return row is not None


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


async def like_tweet(page, tweet_url: str = None) -> bool:
    """Like the tweet on the current page or navigate to tweet_url first."""
    try:
        config = load_config()
        if tweet_url:
            await page.goto(tweet_url, wait_until="domcontentloaded")
            await human_delay(1.5, 3)

        like_btn = await page.query_selector('[data-testid="like"]')
        if like_btn:
            await human_delay(0.5, 1.5)
            await human_click(page, like_btn)
            await human_delay(0.5, 1)
            try:
                toast = await page.query_selector('[data-testid="toast"]')
                if toast:
                    text = (await toast.inner_text()).lower()
                    if "rate limit" in text or "too many" in text or "try again" in text:
                        cooldown = config.get("safety", {}).get("rate_limit_cooldown_minutes", 45)
                        record_rate_limit("like", cooldown, reason=text[:120])
                        return False
            except Exception:
                pass
            return True

        return False

    except Exception as e:
        print(f"❌ Like error: {e}")
        return False


async def like_from_feed(page, max_likes: int = 10):
    """Like tweets from your home feed."""
    config = load_config()
    profile_text = quality.build_relevance_profile(config)
    keywords = quality.relevance_keywords(config)

    if is_limit_reached("like", config["engagement"]["daily_likes"]):
        return

    await set_status("Liking home feed")
    await page.goto("https://x.com/home", wait_until="domcontentloaded")
    await human_delay(2, 3)

    liked = 0
    scrolls = 0
    max_scrolls = random.randint(4, 8)

    while liked < max_likes and scrolls < max_scrolls:
        tweets = await page.query_selector_all('[data-testid="tweet"]')

        for tweet in tweets:
            if liked >= max_likes:
                break

            if is_limit_reached("like", config["engagement"]["daily_likes"]):
                break

            try:
                # Check if already liked
                like_btn = await tweet.query_selector('[data-testid="like"]')
                unlike_btn = await tweet.query_selector('[data-testid="unlike"]')

                if unlike_btn or not like_btn:
                    continue  # Already liked or no button

                # Get tweet text for logging
                text_el = await tweet.query_selector('[data-testid="tweetText"]')
                text = await text_el.inner_text() if text_el else ""
                if not text:
                    continue
                if quality.is_bait(text, config) or not quality.is_english(text):
                    continue

                engagement = await _get_engagement_counts(tweet)
                tweet_info = {"engagement": engagement}
                passes_quality, _ = quality.candidate_passes(text, tweet_info, config, profile_text, keywords)
                if not passes_quality:
                    continue

                # Get author
                author_el = await tweet.query_selector('[data-testid="User-Name"] a')
                author = ""
                if author_el:
                    href = await author_el.get_attribute("href")
                    author = href.strip("/") if href else ""

                await set_status(f"Liking @{author}" if author else "Liking a tweet")
                await human_click(page, like_btn)
                await human_delay(0.8, 2)
                liked += 1

                log_action(
                    action_type="like",
                    target_user=author,
                    content=text[:100],
                    success=True
                )

                # Random pause between likes
                await asyncio.sleep(random.uniform(
                    config["engagement"]["min_delay_seconds"],
                    config["engagement"]["max_delay_seconds"]
                ))
                await maybe_micro_break()

            except Exception:
                continue

        # Scroll down for more tweets
        await human_scroll(page, amount=random.randint(600, 1000))
        await human_delay(1.5, 3)
        scrolls += 1

    print(f"✅ Liked {liked} tweets from feed")




def _normalize_username(value: str) -> str:
    if not value:
        return ""
    name = value.strip().lstrip("@")
    return name.lower()


async def _home_feed_authors(page, max_tweets: int = 50) -> list:
    await page.goto("https://x.com/home", wait_until="domcontentloaded")
    await human_delay(2, 3)

    authors = []
    seen = set()
    scrolls = 0
    max_scrolls = random.randint(2, 4)

    while len(authors) < max_tweets and scrolls < max_scrolls:
        tweets = await page.query_selector_all('[data-testid="tweet"]')
        for tweet in tweets:
            if len(authors) >= max_tweets:
                break
            try:
                author_el = await tweet.query_selector('[data-testid="User-Name"] a')
                if not author_el:
                    continue
                href = await author_el.get_attribute("href")
                if not href:
                    continue
                name = _normalize_username(href.split("?")[0].strip("/").split("/")[0])
                if not name or name in seen:
                    continue
                authors.append(name)
                seen.add(name)
            except Exception:
                continue

        await human_scroll(page, amount=random.randint(600, 1000))
        await human_delay(1.5, 2.5)
        scrolls += 1

    return authors


async def _like_profile_posts(page, username: str, target_likes: int, config: dict) -> int:
    if target_likes <= 0:
        return 0
    profile_text = quality.build_relevance_profile(config)
    keywords = quality.relevance_keywords(config)

    await set_status(f"Profile likes @{username}")
    await page.goto(f"https://x.com/{username}", wait_until="domcontentloaded")
    await human_delay(2, 3)

    liked = 0
    scrolls = 0

    while liked < target_likes and scrolls < 6:
        tweets = await page.query_selector_all('[data-testid="tweet"]')
        for tweet in tweets:
            if liked >= target_likes:
                break
            if is_limit_reached("like", config["engagement"]["daily_likes"]):
                return liked

            try:
                unlike_btn = await tweet.query_selector('[data-testid="unlike"]')
                like_btn = await tweet.query_selector('[data-testid="like"]')
                if unlike_btn or not like_btn:
                    continue

                text_el = await tweet.query_selector('[data-testid="tweetText"]')
                text = await text_el.inner_text() if text_el else ""
                if not text:
                    continue
                if quality.is_bait(text, config) or not quality.is_english(text):
                    continue

                engagement = await _get_engagement_counts(tweet)
                tweet_info = {"engagement": engagement}
                passes_quality, _ = quality.candidate_passes(text, tweet_info, config, profile_text, keywords)
                if not passes_quality:
                    continue

                tweet_url = None
                link_el = await tweet.query_selector('a[href*="/status/"]')
                if link_el:
                    href = await link_el.get_attribute("href")
                    if href:
                        tweet_url = f"https://twitter.com{href.split('?')[0]}"
                        if already_liked(tweet_url):
                            continue

                await human_click(page, like_btn)
                await human_delay(0.8, 2)
                liked += 1

                log_action(
                    action_type="like",
                    target_user=username,
                    content=text[:100],
                    success=True,
                    metadata={"source": "profile", "tweet_url": tweet_url}
                )

                await asyncio.sleep(random.uniform(
                    config["engagement"]["min_delay_seconds"],
                    config["engagement"]["max_delay_seconds"]
                ))

            except Exception:
                continue

        await human_scroll(page, amount=random.randint(700, 1200))
        await human_delay(1.5, 2.5)
        scrolls += 1

    return liked


async def like_profile_posts(page, username: str, min_posts: int = 3, max_posts: int = 4, config: dict = None) -> int:
    """Like multiple posts on a user's profile."""
    config = config or load_config()
    if max_posts < min_posts:
        max_posts = min_posts
    target_likes = random.randint(min_posts, max_posts) if max_posts > 0 else 0
    if target_likes <= 0:
        return 0
    return await _like_profile_posts(page, username, target_likes, config)


async def like_from_profiles(page):
    """Visit random profiles from home feed and like multiple posts per profile."""
    config = load_config()
    discovery = config.get("discovery", {})

    if not discovery.get("profile_like_from_home_enabled", False):
        return

    max_profiles = int(discovery.get("profile_like_profiles_per_session", 0) or 0)
    if max_profiles <= 0:
        return

    if is_limit_reached("like", config["engagement"]["daily_likes"]):
        return

    min_posts = int(discovery.get("profile_like_min_posts", 3) or 0)
    max_posts = int(discovery.get("profile_like_max_posts", 6) or 0)
    if max_posts < min_posts:
        max_posts = min_posts

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    self_username = _normalize_username(os.getenv("TWITTER_USERNAME", ""))

    authors = await _home_feed_authors(page, max_tweets=discovery.get("max_home_tweets_scanned", 50))
    authors = [a for a in authors if a and a != self_username]

    if not authors:
        print("⚠️  No home feed authors found for profile likes")
        return

    random.shuffle(authors)
    selected = authors[:max_profiles]
    total_liked = 0

    for username in selected:
        if is_limit_reached("like", config["engagement"]["daily_likes"]):
            break
        target_likes = random.randint(min_posts, max_posts) if max_posts > 0 else 0
        print(f"👤 Visiting @{username} — liking {target_likes} posts")
        total_liked += await _like_profile_posts(page, username, target_likes, config)

    if total_liked > 0:
        print(f"✅ Liked {total_liked} posts across {len(selected)} profiles")
