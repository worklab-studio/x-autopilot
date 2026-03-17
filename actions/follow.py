"""
actions/follow.py — Smart follow/unfollow logic
Follows engaged people in your niche.
Unfollows non-followers after 6 days to keep ratio healthy.
"""

import asyncio
import random
import sqlite3
import os
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta
from agent.browser import human_delay, human_click, human_scroll, human_navigate
from agent.targets import get_target_accounts, load_targets
from agent.logger import log_action, is_limit_reached, DB_PATH
from agent.status_overlay import set_status
from agent import quality
from agent.pacing import record_rate_limit
from agent.humanize import maybe_micro_break
from actions.reply import get_latest_tweets
from agent.dynamic_config import load_config_with_dynamic
from actions.like import _home_feed_authors
from dotenv import load_dotenv

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config():
    return load_config_with_dynamic(CONFIG_PATH)


def already_followed(username: str) -> bool:
    """Check if we've already followed this person."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id FROM actions
        WHERE action_type = 'follow'
        AND target_user = ?
        AND success = 1
        LIMIT 1
    """, (username,))
    row = c.fetchone()
    conn.close()
    return row is not None


def _normalize_username(value: str) -> str:
    if not value:
        return ""
    name = value.strip().lstrip("@")
    return name.lower()


def record_follow(username: str, followers: int):
    """Record a follow for future unfollow tracking."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Store follow date for unfollow logic
    c.execute("""
        INSERT OR IGNORE INTO actions
        (timestamp, action_type, target_user, target_user_followers, success, metadata)
        VALUES (?, 'follow_tracked', ?, ?, 1, '{"for_unfollow": true}')
    """, (datetime.now().isoformat(), username, followers))
    conn.commit()
    conn.close()


async def follow_user(page, username: str) -> bool:
    """Follow a Twitter user."""
    try:
        config = load_config()
        await human_navigate(page, f"https://x.com/{username}")
        if random.random() < 0.6:
            await human_scroll(page, amount=random.randint(200, 500))
            await human_delay(0.6, 1.2)

        # Find the Follow button
        follow_selectors = [
            '[data-testid="placementTracking"] [role="button"]:has-text("Follow")',
            '[data-testid*="follow"]',
            f'[aria-label="Follow @{username}"]',
        ]

        for selector in follow_selectors:
            try:
                btn = await page.wait_for_selector(selector, timeout=3000)
                if btn:
                    text = await btn.inner_text()
                    if "Follow" in text and "Following" not in text and "Unfollow" not in text:
                        await human_delay(0.5, 1.5)
                        await human_click(page, btn)
                        await human_delay(1, 2)
                        try:
                            toast = await page.query_selector('[data-testid="toast"]')
                            if toast:
                                text = (await toast.inner_text()).lower()
                                if "rate limit" in text or "too many" in text or "try again" in text:
                                    cooldown = config.get("safety", {}).get("rate_limit_cooldown_minutes", 45)
                                    record_rate_limit("follow", cooldown, reason=text[:120])
                                    return False
                        except Exception:
                            pass
                        return True
            except Exception:
                continue

        return False

    except Exception as e:
        print(f"❌ Follow error for @{username}: {e}")
        return False


async def get_account_followers_list(page, username: str, limit: int = 30) -> list:
    """
    Get followers of a target account — these are pre-qualified leads.
    People who follow big accounts in your niche are likely to follow you.
    """
    usernames = []
    try:
        # Search for the user first to make it look like human behavior
        query = urllib.parse.quote(username)
        url = f"https://x.com/search?q={query}&src=typed_query&f=user"
        await human_navigate(page, url)

        # Look for the user in search results and click their profile
        user_cells = await page.query_selector_all('[data-testid="UserCell"]')
        if user_cells:
            # We assume the first one is our target
            await human_click(page, user_cells[0])
            await human_delay(2, 4)
        else:
            # Fallback directly to profile
            await human_navigate(page, f"https://x.com/{username}")

        # Now click their Followers link instead of direct navigation
        followers_link = await page.query_selector(f'a[href*="/{username}/followers" i]')
        if followers_link:
            await human_click(page, followers_link)
            await human_delay(2, 4)
        else:
            # Extreme fallback
            await human_navigate(page, f"https://x.com/{username}/followers")

        # Scroll and collect usernames
        max_scrolls = random.randint(2, 4)
        for _ in range(max_scrolls):
            cells = await page.query_selector_all('[data-testid="UserCell"]')
            for cell in cells:
                try:
                    link = await cell.query_selector('a[href*="/"]')
                    if link:
                        href = await link.get_attribute("href")
                        if href and href.startswith("/") and "/" not in href[1:]:
                            uname = href.strip("/")
                            if uname and uname not in usernames:
                                usernames.append(uname)
                except Exception:
                    continue

            if len(usernames) >= limit:
                break

            await human_scroll(page, amount=800)
            await human_delay(1.5, 3)

        return usernames[:limit]

    except Exception as e:
        print(f"⚠️  Could not get followers of @{username}: {e}")
        return []


async def get_mentions_engagers(page, limit: int = 20) -> list:
    """Get users who mentioned or replied to us (engagement source)."""
    usernames = []
    try:
        await human_navigate(page, "https://x.com/notifications/mentions")

        for _ in range(3):
            tweets = await page.query_selector_all('[data-testid="tweet"]')
            for tweet in tweets:
                try:
                    author_el = await tweet.query_selector('[data-testid="User-Name"] a')
                    if not author_el:
                        continue
                    href = await author_el.get_attribute("href")
                    name = _normalize_username(href.split("?")[0].strip("/").split("/")[0] if href else "")
                    if name and name not in usernames:
                        usernames.append(name)
                except Exception:
                    continue

            if len(usernames) >= limit:
                break

            await human_scroll(page, amount=900)
            await human_delay(1.5, 3)

        return usernames[:limit]

    except Exception as e:
        print(f"⚠️  Could not get mentions engagers: {e}")
        return []


async def _candidate_ok_for_follow(page, username: str, config: dict, profile_text: str, keywords: list) -> bool:
    tweets = await get_latest_tweets(page, username, count=1, allow_self=True)
    if not tweets:
        return False
    tweet = tweets[0]
    text = tweet.get("text", "")
    if not text:
        return False
    if quality.is_bait(text, config) or not quality.is_english(text):
        return False
    passes_quality, _ = quality.candidate_passes(text, tweet, config, profile_text, keywords)
    return passes_quality


async def run_follow_session(page, max_follows: int = 10):
    """
    Main follow session.
    Gets followers of target accounts and follows them.
    """
    config = load_config()
    targets_cfg = config.get("targets", {})
    profile_text = quality.build_relevance_profile(config)
    keywords = quality.relevance_keywords(config)

    if is_limit_reached("follow", config["engagement"]["daily_follows"]):
        print("⚠️  Daily follow limit reached")
        return

    followed_count = 0

    if targets_cfg.get("follow_from_mentions_enabled", True):
        max_from_mentions = int(targets_cfg.get("follow_from_mentions_max_per_session", 3) or 0)
        mentioners = await get_mentions_engagers(page, limit=max_from_mentions * 3)
        mention_followed = 0

        for username in mentioners:
            if followed_count >= max_follows or mention_followed >= max_from_mentions:
                break

            if is_limit_reached("follow", config["engagement"]["daily_follows"]):
                break

            if already_followed(username):
                continue

            if len(username) > 20 or username.replace("_", "").isdigit():
                continue

            if not await _candidate_ok_for_follow(page, username, config, profile_text, keywords):
                continue

            await set_status(f"Following @{username} (mentions)")
            print(f"   ↳ Following @{username} from mentions...")
            success = await follow_user(page, username)

            log_action(
                action_type="follow",
                target_user=username,
                success=success,
                metadata={"source": "mentions"}
            )

            if success:
                followed_count += 1
                mention_followed += 1
                print(f"   ✅ Followed @{username}")

            delay = random.uniform(
                config["engagement"]["min_delay_seconds"] * 2,
                config["engagement"]["max_delay_seconds"] * 1.5
            )
            await asyncio.sleep(delay)
            await maybe_micro_break()

    if targets_cfg.get("follow_from_home_enabled", False):
        max_from_home = int(targets_cfg.get("follow_from_home_max_per_session", 2) or 0)
        home_followed = 0
        if max_from_home > 0 and followed_count < max_follows:
            load_dotenv()
            self_username = _normalize_username(os.getenv("TWITTER_USERNAME", ""))
            authors = await _home_feed_authors(page, max_tweets=config.get("discovery", {}).get("max_home_tweets_scanned", 50))
            random.shuffle(authors)

            for username in authors:
                if followed_count >= max_follows or home_followed >= max_from_home:
                    break
                if is_limit_reached("follow", config["engagement"]["daily_follows"]):
                    break
                if not username or username == self_username:
                    continue
                if already_followed(username):
                    continue
                if len(username) > 20 or username.replace("_", "").isdigit():
                    continue
                if not await _candidate_ok_for_follow(page, username, config, profile_text, keywords):
                    continue

                await set_status(f"Following @{username} (home)")
                print(f"   ↳ Following @{username} from home feed...")
                success = await follow_user(page, username)

                log_action(
                    action_type="follow",
                    target_user=username,
                    success=success,
                    metadata={"source": "home_feed"}
                )

                if success:
                    followed_count += 1
                    home_followed += 1
                    print(f"   ✅ Followed @{username}")

                delay = random.uniform(
                    config["engagement"]["min_delay_seconds"] * 2,
                    config["engagement"]["max_delay_seconds"] * 1.5
                )
                await asyncio.sleep(delay)
                await maybe_micro_break()

    targets = load_targets()
    small_only = targets_cfg.get("follow_from_small_targets_only", True)
    source_pool = []
    if small_only and targets.get("small"):
        source_pool = targets.get("small", [])
    else:
        source_pool = targets.get("small", []) + targets.get("peer", []) + targets.get("big", [])

    if not source_pool:
        source_pool = get_target_accounts()
    if not source_pool:
        source_pool = config.get("target_accounts", [])
    if not source_pool:
        print("⚠️  No target accounts available for follow session")
        return

    source_account = random.choice(source_pool)

    await set_status(f"Collecting followers of @{source_account}")
    print(f"\n👥 Getting followers of @{source_account}...")
    followers_to_follow = await get_account_followers_list(page, source_account, limit=40)

    for username in followers_to_follow:
        if followed_count >= max_follows:
            break

        if is_limit_reached("follow", config["engagement"]["daily_follows"]):
            break

        if already_followed(username):
            continue

        # Skip obvious bots (no letters, very long names, etc.)
        if len(username) > 20 or username.replace("_", "").isdigit():
            continue

        if not await _candidate_ok_for_follow(page, username, config, profile_text, keywords):
            continue

        await set_status(f"Following @{username}")
        print(f"   ↳ Following @{username}...")
        success = await follow_user(page, username)

        if success:
            followed_count += 1
            log_action(
                action_type="follow",
                target_user=username,
                success=True,
                metadata={"source": source_account}
            )
            print(f"   ✅ Followed @{username}")
        else:
            log_action(
                action_type="follow",
                target_user=username,
                success=False
            )

        # Human pause between follows
        delay = random.uniform(
            config["engagement"]["min_delay_seconds"] * 2,
            config["engagement"]["max_delay_seconds"] * 1.5
        )
        await asyncio.sleep(delay)
        await maybe_micro_break()

    print(f"\n✅ Follow session done — {followed_count} new follows")




async def run_unfollow_session(page, max_unfollows: int = 15):
    """
    Unfollow people who haven't followed back after 6 days.
    Keeps your following/follower ratio healthy.
    """
    config = load_config()
    unfollow_after_days = config["safety"].get("unfollow_non_followers_after_days", 6)

    # Get accounts we followed more than N days ago
    cutoff = (datetime.now() - timedelta(days=unfollow_after_days)).isoformat()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT target_user FROM actions
        WHERE action_type = 'follow'
        AND success = 1
        AND timestamp < ?
        AND target_user NOT IN (
            SELECT target_user FROM actions WHERE action_type = 'unfollow'
        )
        LIMIT ?
    """, (cutoff, max_unfollows))
    rows = c.fetchall()
    conn.close()

    if not rows:
        print("✅ No accounts to unfollow right now")
        return

    unfollowed = 0
    for (username,) in rows:
        success = await _unfollow_user(page, username)
        if success:
            unfollowed += 1
            log_action(action_type="unfollow", target_user=username, success=True)
            print(f"   ↩️  Unfollowed @{username}")

        delay = random.uniform(10, 25)
        await asyncio.sleep(delay)

    print(f"\n✅ Unfollow session done — {unfollowed} unfollowed")


async def _unfollow_user(page, username: str) -> bool:
    """Unfollow a user."""
    try:
        await human_navigate(page, f"https://x.com/{username}")

        # Find Following button (which we click to unfollow)
        btn = await page.query_selector(f'[aria-label="Following @{username}"]')
        if not btn:
            btn = await page.query_selector('[data-testid*="unfollow"]')

        if btn:
            await human_click(page, btn)
            await human_delay(1, 2)

            # Confirm unfollow dialog if it appears
            confirm = await page.query_selector('[data-testid="confirmationSheetConfirm"]')
            if confirm:
                await human_click(page, confirm)
                await human_delay(1, 2)

            return True

        return False

    except Exception as e:
        print(f"❌ Unfollow error for @{username}: {e}")
        return False
