"""
actions/tweet.py — Tweet posting action
Checks the approval queue and posts any approved tweets.
Also generates new tweets and adds them to the queue for your approval.
"""

import asyncio
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from agent.browser import human_delay, human_type, human_click
from agent.logger import (
    log_action, is_limit_reached, add_to_tweet_queue,
    get_pending_tweets, approve_tweet, get_daily_count
)
from agent.status_overlay import set_status
from agent.mentions import apply_tool_mentions, type_with_mentions
from ai.tweet_writer import generate_tweet, generate_promo_tweet
from agent.promotions import load_promotions
from actions.reply import get_latest_tweets, reply_to_tweet
from agent.dynamic_config import load_config_with_dynamic

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
load_dotenv()


def load_config():
    return load_config_with_dynamic(CONFIG_PATH)


async def generate_and_queue_tweet(tweet_type: str = "auto", topic: str = None):
    """
    Generate a tweet using AI and add it to the approval queue.
    You'll see it in the dashboard and approve it before it goes live.
    """
    config = load_config()

    print(f"\n🤖 Generating tweet (type: {tweet_type})...")
    await set_status(f"Generating tweet ({tweet_type})")

    tweet_content = generate_tweet(
        topic=topic,
        tweet_type=tweet_type
    )
    tweet_content = apply_tool_mentions(tweet_content, config)

    print(f"📝 Generated: \"{tweet_content}\"")

    # Add to queue — won't post until you approve
    tweet_id = add_to_tweet_queue(
        content=tweet_content,
        scheduled_for=_next_tweet_time(config)
    )

    log_action(
        action_type="tweet_generated",
        content=tweet_content,
        metadata={"tweet_id": tweet_id, "type": tweet_type}
    )

    return tweet_id, tweet_content


async def generate_and_queue_promo_tweet(config: dict):
    """Generate a subtle promo tweet and add it to the queue."""
    promotions = load_promotions()
    if not promotions:
        return None, None

    mentions_per_day = config.get("promotions", {}).get("mentions_per_day", 3)
    if is_limit_reached("promo_generated", mentions_per_day):
        return None, None

    promo = promotions[datetime.now().day % len(promotions)]
    await set_status("Generating promo tweet")
    content = generate_promo_tweet(promo)
    content = apply_tool_mentions(content, config)
    tweet_id = add_to_tweet_queue(
        content=content,
        scheduled_for=_next_tweet_time(config)
    )

    log_action(
        action_type="promo_generated",
        content=content,
        success=True,
        metadata={"product": promo.get("name"), "url": promo.get("url")}
    )
    return tweet_id, content


async def post_approved_tweets(page):
    """
    Check for approved tweets and post them if it's the right time.
    Called by the scheduler throughout the day.
    """
    config = load_config()

    if is_limit_reached("tweet", config["posting"]["tweets_per_day"]):
        return "limit"

    from agent.logger import DB_PATH
    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, content, thread_id, thread_index, media_path, media_type
        FROM tweet_queue
        WHERE status = 'approved'
        ORDER BY approved_at ASC
    """)
    approved = c.fetchall()
    conn.close()

    if not approved:
        return "empty"

    next_item = None
    for row in approved:
        tweet_id, content, thread_id, thread_index, media_path, media_type = row
        if not thread_id:
            next_item = ("single", tweet_id, content, media_path, media_type)
            break

        # Check thread completeness (no pending parts)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT id, content, thread_index, status, media_path, media_type
            FROM tweet_queue
            WHERE thread_id = ?
            ORDER BY thread_index ASC
        """, (thread_id,))
        parts = c.fetchall()
        conn.close()

        if not parts:
            continue

        if any(p[3] != "approved" for p in parts):
            continue

        thread_contents = [p[1] for p in parts]
        if any(not (t or "").strip() for t in thread_contents):
            continue

        next_item = ("thread", thread_id, parts)
        break

    if not next_item:
        return "empty"

    if next_item[0] == "single":
        _, tweet_id, content, media_path, media_type = next_item
        await set_status("Posting tweet")
        success = await _post_tweet(page, content, media_path=media_path, media_type=media_type)
        if success:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                UPDATE tweet_queue
                SET status = 'posted', posted_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), tweet_id))
            conn.commit()
            conn.close()

            log_action(action_type="tweet", content=content, success=True)
            print(f"✅ Tweet posted: \"{content[:60]}...\"")
            return "posted"
        log_action(action_type="tweet", content=content, success=False, error="Failed to post tweet")
        return "failed"

    # Thread posting
    _, thread_id, parts = next_item
    thread_contents = [p[1] for p in parts]
    daily_limit = config["posting"]["tweets_per_day"]
    remaining = daily_limit - get_daily_count("tweet")
    if remaining < len(thread_contents):
        print("⚠️  Not enough daily tweet quota to post thread")
        return "skipped"

    thread_parts = [
        {
            "content": p[1],
            "media_path": p[4],
            "media_type": p[5],
        } for p in parts
    ]
    await set_status("Posting thread")
    success = await _post_thread(page, thread_parts)
    if success:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            UPDATE tweet_queue
            SET status = 'posted', posted_at = ?
            WHERE thread_id = ?
        """, (datetime.now().isoformat(), thread_id))
        conn.commit()
        conn.close()

        for content in thread_contents:
            log_action(action_type="tweet", content=content, success=True, metadata={"thread_id": thread_id})
        print(f"✅ Thread posted: {len(thread_contents)} tweets")
        return "posted"
    for content in thread_contents:
        log_action(action_type="tweet", content=content, success=False, error="Failed to post thread", metadata={"thread_id": thread_id})
    return "failed"


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


async def _post_tweet(page, content: str, media_path: str = None, media_type: str = None) -> bool:
    """Actually post a tweet using the browser."""
    try:
        config = load_config()
        content = apply_tool_mentions(content, config)

        # Navigate to home
        await page.goto("https://x.com/home", wait_until="domcontentloaded")
        await human_delay(2, 4)

        # Click the tweet compose box
        compose_selectors = [
            '[data-testid="tweetTextarea_0"]',
            '[placeholder="What is happening?!"]',
            '[aria-label="Tweet text"]',
        ]

        compose_box = None
        for selector in compose_selectors:
            try:
                compose_box = await page.wait_for_selector(selector, timeout=5000)
                if compose_box:
                    break
            except Exception:
                continue

        if not compose_box:
            print("❌ Could not find tweet compose box")
            return False

        await human_click(page, compose_box)
        await human_delay(0.5, 1.2)

        # Type the tweet like a human
        await type_with_mentions(page, compose_box, content)
        await human_delay(1, 2.5)

        if media_path:
            attached = await _attach_media(page, media_path)
            if attached:
                await _wait_for_post_enabled(page)

        # Click the Post button
        post_selectors = [
            '[data-testid="tweetButtonInline"]',
            '[data-testid="tweetButton"]',
        ]

        posted = False
        for selector in post_selectors:
            try:
                post_btn = await page.wait_for_selector(selector, timeout=3000)
                if post_btn:
                    await human_delay(0.8, 1.5)
                    await human_click(page, post_btn)
                    posted = True
                    break
            except Exception:
                continue

        if posted:
            await human_delay(2, 3)
            return True
        else:
            print("❌ Could not find post button")
            return False

    except Exception as e:
        print(f"❌ Tweet posting error: {e}")
        return False


async def _get_latest_self_tweet_url(page) -> str:
    username = os.getenv("TWITTER_USERNAME", "").strip().lstrip("@")
    if not username:
        return ""
    tweets = await get_latest_tweets(page, username, count=1, allow_self=True)
    if tweets:
        return tweets[0].get("url", "")
    return ""


async def _post_thread(page, parts: list) -> bool:
    if not parts:
        return False

    first = parts[0]
    success = await _post_tweet(
        page,
        first.get("content", ""),
        media_path=first.get("media_path"),
        media_type=first.get("media_type"),
    )
    if not success:
        return False

    await human_delay(2, 4)
    last_url = await _get_latest_self_tweet_url(page)
    if not last_url:
        return False

    for part in parts[1:]:
        success = await reply_to_tweet(
            page,
            last_url,
            part.get("content", ""),
            media_path=part.get("media_path"),
            media_type=part.get("media_type"),
        )
        if not success:
            return False
        await human_delay(2, 4)
        last_url = await _get_latest_self_tweet_url(page)
        if not last_url:
            return False

    return True


def _next_tweet_time(config) -> str:
    """Return the next scheduled tweet time."""
    tweet_times = config["posting"].get("tweet_times", ["09:30", "19:00"])
    now = datetime.now()
    current_time = now.strftime("%H:%M")

    for t in tweet_times:
        if t > current_time:
            return f"{now.strftime('%Y-%m-%d')} {t}"

    # All times passed today — schedule for tomorrow
    from datetime import timedelta
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    return f"{tomorrow} {tweet_times[0]}"
