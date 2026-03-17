"""
target_discovery.py — Automatically discover and add target accounts.
Scans niche hashtags, checks profile bio + follower count for fit,
and adds qualifying accounts to data/targets.json.

No hardcoded usernames — the agent builds its own target list.
"""

import asyncio
import os
import random
from pathlib import Path

from agent.browser import human_delay, human_navigate, human_scroll
from agent.logger import log_action, is_limit_reached
from agent.targets import add_target, get_target_accounts
from agent import quality
from agent.dynamic_config import load_config_with_dynamic
from agent.status_overlay import set_status
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _load_config() -> dict:
    return load_config_with_dynamic(CONFIG_PATH)


def _parse_follower_count(text: str) -> int:
    text = text.strip().replace(",", "")
    if "K" in text.upper():
        return int(float(text.upper().replace("K", "")) * 1000)
    elif "M" in text.upper():
        return int(float(text.upper().replace("M", "")) * 1000000)
    try:
        return int(text)
    except Exception:
        return 0


async def discover_new_targets(page, max_to_add: int = 5) -> int:
    """
    Scan niche hashtags for profiles that match the agent's voice/niche.
    Checks bio relevance and follower count (assigns correct tier).
    Adds qualifying accounts to data/targets.json.
    Returns number of new targets added.
    """
    config = _load_config()
    settings = config.get("targets", {})

    if not settings.get("auto_add_enabled", False):
        return 0

    max_per_day = settings.get("auto_add_max_per_day", 6)
    if is_limit_reached("target_added", max_per_day):
        return 0

    discovery = config.get("discovery", {})
    hashtags = discovery.get("hashtags", [])
    if not hashtags:
        return 0

    profile_text = quality.build_relevance_profile(config)
    keywords = quality.relevance_keywords(config)
    existing = set(get_target_accounts())
    self_username = os.getenv("TWITTER_USERNAME", "").strip().lstrip("@").lower()

    # ── Step 1: Collect candidate usernames from hashtag searches ─────────────
    candidates = {}  # username → sample tweet text for quick pre-filter

    scan_tags = random.sample(hashtags, min(2, len(hashtags)))
    for hashtag in scan_tags:
        if len(candidates) >= max_to_add * 5:
            break
        try:
            await set_status(f"Discovering targets via #{hashtag}")
            await human_navigate(
                page,
                f"https://x.com/search?q=%23{hashtag}&src=typed_query&f=live",
            )
            await human_delay(2, 4)
            await human_scroll(page, amount=random.randint(400, 800))
            await human_delay(1, 2)

            articles = await page.query_selector_all('[data-testid="tweet"]')
            for article in articles:
                if len(candidates) >= max_to_add * 5:
                    break
                try:
                    author_el = await article.query_selector('[data-testid="User-Name"] a')
                    if not author_el:
                        continue
                    href = await author_el.get_attribute("href")
                    if not href:
                        continue
                    username = href.strip("/").split("/")[0].split("?")[0].lower()
                    if not username or username == self_username:
                        continue
                    if username in existing or username in candidates:
                        continue
                    text_el = await article.query_selector('[data-testid="tweetText"]')
                    tweet_text = await text_el.inner_text() if text_el else ""
                    candidates[username] = tweet_text
                except Exception:
                    continue
        except Exception as e:
            print(f"⚠️  Discovery: could not scan #{hashtag}: {e}")
            continue

    if not candidates:
        return 0

    print(f"🔍 Target discovery: evaluating {len(candidates)} candidate profiles...")
    added = 0

    # ── Step 2: Visit each profile — check bio relevance + follower count ─────
    for username, sample_text in list(candidates.items()):
        if added >= max_to_add:
            break
        if is_limit_reached("target_added", max_per_day):
            break

        try:
            await set_status(f"Evaluating @{username}")
            await human_navigate(page, f"https://x.com/{username}")
            await human_delay(1.5, 2.5)

            # Follower count
            followers = 0
            try:
                el = await page.wait_for_selector(
                    f'[href*="/{username}/followers" i] span span',
                    timeout=6000,
                )
                if el:
                    followers = _parse_follower_count(await el.inner_text())
            except Exception:
                pass

            # Bio text
            bio = ""
            try:
                bio_el = await page.query_selector('[data-testid="UserDescription"]')
                if bio_el:
                    bio = (await bio_el.inner_text()).strip()
            except Exception:
                pass

            # Relevance: bio + sample tweet together
            relevance_text = f"{bio} {sample_text}".strip()
            if not relevance_text:
                continue

            passes, _ = quality.candidate_passes(
                relevance_text,
                {"engagement": {}},
                config,
                profile_text,
                keywords,
            )
            if not passes:
                continue

            # Add with tier automatically determined by follower count
            add_target(username, followers=followers)
            log_action(
                action_type="target_added",
                target_user=username,
                target_user_followers=followers,
                success=True,
                metadata={"source": "hashtag_discovery", "bio": bio[:100]},
            )
            existing.add(username)
            added += 1
            print(f"   ✅ Added @{username} as target ({followers:,} followers)")

            await human_delay(1, 2)

        except Exception as e:
            print(f"   ⚠️  Could not evaluate @{username}: {e}")
            continue

    if added:
        print(f"✅ Target discovery: added {added} new target(s)")
    else:
        print("🔍 Target discovery: no new qualifying targets found")

    return added
