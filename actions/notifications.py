"""
actions/notifications.py — React to notifications (mentions + follows)
"""

import asyncio
import random
import sqlite3
from pathlib import Path

from agent.browser import human_delay, human_click, human_scroll
from agent.logger import log_action, is_limit_reached, DB_PATH
from agent.status_overlay import set_status
from agent import quality
from ai.tweet_writer import generate_reply_with_meta, generate_dm_welcome
from actions.like import like_profile_posts
from actions.dm import send_dm
from actions.reply import (
    already_replied_to,
    get_follower_count,
    get_tier,
    reply_to_tweet,
    _parse_tweet_article,
)
from agent.dynamic_config import load_config_with_dynamic

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config():
    return load_config_with_dynamic(CONFIG_PATH)


def _get_self_username() -> str:
    try:
        from dotenv import load_dotenv
        import os
        load_dotenv()
        return os.getenv("TWITTER_USERNAME", "").strip().lstrip("@").lower()
    except Exception:
        return ""


def _normalize_username(value: str) -> str:
    if not value:
        return ""
    name = value.strip().lstrip("@")
    return name.lower()


def _already_welcomed(username: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id FROM actions
        WHERE action_type = 'dm'
        AND target_user = ?
        AND metadata LIKE '%welcome_follow%'
        LIMIT 1
    """, (username,))
    row = c.fetchone()
    conn.close()
    return row is not None


async def _collect_mentions(page, max_tweets: int = 20) -> list:
    await page.goto("https://x.com/notifications/mentions", wait_until="domcontentloaded")
    await human_delay(2, 3)

    tweets = []
    seen = set()
    scrolls = 0

    while len(tweets) < max_tweets and scrolls < 2:
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
                break

        await human_scroll(page, amount=random.randint(600, 1000))
        await human_delay(1.5, 2.5)
        scrolls += 1

    return tweets


async def _collect_conversation_context(page, tweet_url: str, config: dict) -> dict:
    await page.goto(tweet_url, wait_until="domcontentloaded")
    await human_delay(2, 4)

    expand_selectors = [
        'div[role="button"]:has-text("Show more")',
        'div[role="button"]:has-text("Show replies")',
        'div[role="button"]:has-text("Show more replies")',
        'div[role="button"]:has-text("Show this thread")',
        'a:has-text("Show this thread")',
        '[data-testid="showMoreText"]',
    ]

    for _ in range(3):
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

    self_username = _get_self_username()
    replying_to_self = False
    try:
        ctx = await page.query_selector('[data-testid="replyContext"]')
        if ctx and self_username:
            link = await ctx.query_selector(f'a[href="/{self_username}"]')
            if link:
                replying_to_self = True
    except Exception:
        pass

    collected = []
    has_video = False

    for _ in range(4):
        articles = await page.query_selector_all('[data-testid="tweet"]')
        for article in articles:
            parsed = await _parse_tweet_article(article, allow_self=True)
            if not parsed:
                continue
            if parsed.get("has_video"):
                has_video = True
            text = parsed.get("text")
            if text and text not in collected:
                collected.append(text)
            if len(collected) >= 10:
                break
        if len(collected) >= 10:
            break
        await human_scroll(page, amount=900)
        await human_delay(1.5, 2.5)

    thread_text = "\n\n".join(collected).strip()
    return {
        "thread_text": thread_text,
        "has_video": has_video,
        "replying_to_self": replying_to_self,
    }


async def _collect_follow_notifications(page, max_users: int = 10) -> list:
    await page.goto("https://x.com/notifications", wait_until="domcontentloaded")
    await human_delay(2, 3)

    users = []
    seen = set()

    badges = await page.query_selector_all('span:has-text("Followed you"), div:has-text("Followed you")')
    for badge in badges:
        if len(users) >= max_users:
            break
        try:
            article = await badge.evaluate_handle("el => el.closest('article')")
            if not article:
                continue
            link = await article.query_selector('[data-testid="User-Name"] a')
            if not link:
                link = await article.query_selector('a[href^="/"]')
            if not link:
                continue
            href = await link.get_attribute("href")
            name = _normalize_username(href.split("?")[0].strip("/").split("/")[0] if href else "")
            if not name or "/" in name or name in seen:
                continue
            seen.add(name)
            users.append(name)
        except Exception:
            continue

    return users


async def run_notifications_session(page):
    config = load_config()
    settings = config.get("notifications", {})
    self_username = _get_self_username()

    if not settings.get("reply_to_mentions", False) and not settings.get("follow_welcome_enabled", False):
        return

    profile_text = quality.build_relevance_profile(config)
    keywords = quality.relevance_keywords(config)

    # Replies to mentions (replies to our replies)
    if settings.get("reply_to_mentions", False):
        max_replies = int(settings.get("max_reply_notifications_per_session", 3) or 0)
        if max_replies > 0 and not is_limit_reached("reply", config["engagement"]["daily_replies"]):
            print("\n🔔 Notifications: mentions")
            await set_status("Notifications: mentions")
            mentions = await _collect_mentions(page, max_tweets=max_replies * 4)
            replied = 0

            for tweet in mentions:
                if replied >= max_replies:
                    break
                if is_limit_reached("reply", config["engagement"]["daily_replies"]):
                    break

                if already_replied_to(tweet["url"]):
                    continue
                if tweet.get("author", "").lower() == self_username:
                    continue
                if tweet.get("has_video"):
                    continue
                if quality.is_bait(tweet.get("text", ""), config) or not quality.is_english(tweet.get("text", "")):
                    continue

                thread_context = await _collect_conversation_context(page, tweet["url"], config)
                if not thread_context.get("replying_to_self"):
                    continue
                if thread_context.get("has_video"):
                    continue

                thread_text = thread_context.get("thread_text") or tweet.get("text", "")
                if not thread_text:
                    continue

                if quality.text_quality_score(thread_text, config) < config.get("discovery", {}).get("thread_quality_min_score", 0.0):
                    continue
                topic_ratio = quality.thread_topic_ratio(thread_text, config, profile_text, keywords)
                if topic_ratio < config.get("discovery", {}).get("thread_topic_min_ratio", 0.0):
                    continue

                passes_quality, _ = quality.candidate_passes(thread_text, tweet, config, profile_text, keywords)
                if not passes_quality:
                    continue

                followers = await get_follower_count(page, tweet["author"])
                tier = get_tier(followers, config)

                reply_payload = generate_reply_with_meta(
                    tweet_text=thread_text,
                    author=tweet["author"],
                    author_followers=followers,
                    tier=tier,
                    extra_context="Follow-up from notifications. Full thread context included."
                )
                reply_text = reply_payload.get("text") if reply_payload else ""
                if not reply_text:
                    continue

                success = await reply_to_tweet(page, tweet["url"], reply_text)
                log_action(
                    action_type="reply",
                    target_user=tweet["author"],
                    target_user_followers=followers,
                    tier=tier,
                    content=reply_text,
                    success=success,
                    metadata={
                        "tweet_url": tweet["url"],
                        "source": "notifications",
                        **(reply_payload.get("meta") or {})
                    }
                )

                if success:
                    replied += 1

                delay = random.uniform(
                    config["engagement"]["min_delay_seconds"],
                    config["engagement"]["max_delay_seconds"]
                )
                await asyncio.sleep(delay)

    # Welcome new followers: like 3-4 posts + DM
    if settings.get("follow_welcome_enabled", False):
        max_welcomes = int(settings.get("max_follow_welcomes_per_session", 3) or 0)
        if max_welcomes > 0:
            print("\n🔔 Notifications: follows")
            await set_status("Notifications: new followers")
            followers = await _collect_follow_notifications(page, max_users=max_welcomes * 2)
            welcomed = 0

            for username in followers:
                if welcomed >= max_welcomes:
                    break
                if _already_welcomed(username):
                    continue

                if is_limit_reached("dm", config["engagement"]["daily_dms"]):
                    break

                min_posts = int(settings.get("follow_welcome_like_min_posts", 3) or 0)
                max_posts = int(settings.get("follow_welcome_like_max_posts", 4) or 0)

                await like_profile_posts(page, username, min_posts=min_posts, max_posts=max_posts, config=config)

                dm_text = generate_dm_welcome(username=username)
                await set_status(f"Welcome DM @{username}")
                success = await send_dm(page, username, dm_text, skip_navigation=True)

                log_action(
                    action_type="dm",
                    target_user=username,
                    content=dm_text,
                    success=success,
                    metadata={"source": "welcome_follow"}
                )

                if success:
                    welcomed += 1

                await asyncio.sleep(random.uniform(30, 90))
