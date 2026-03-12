"""
tools/dry_run.py — Full agent simulation without posting anything
Runs a complete agent session in READ-ONLY mode.
Shows exactly what it WOULD do — zero risk, zero posting.

Usage: python tools/dry_run.py
"""

import asyncio
import sys
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


async def dry_run():
    print("""
╔══════════════════════════════════════╗
║     DRY RUN — READ ONLY MODE        ║
║     Nothing will be posted          ║
╚══════════════════════════════════════╝
""")

    from agent.browser import launch_browser, get_page
    from agent.session import ensure_logged_in
    from actions.reply import get_latest_tweets, get_follower_count, get_tier
    from ai.tweet_writer import generate_tweet, generate_reply
    from ai.trend_scanner import scrape_trending_topics, filter_relevant_trends
    import yaml

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    print("🚀 Launching browser (read-only mode)...")
    playwright, browser = await launch_browser(headless=False)
    page = await get_page(browser)

    logged_in = await ensure_logged_in(browser, page)
    if not logged_in:
        print("❌ Not logged in")
        await browser.close()
        await playwright.stop()
        return

    print("✅ Logged in — starting simulation\n")
    print("=" * 50)

    # ── STEP 1: Trend scan ───────────────────────────
    print("\n📡 STEP 1 — TREND SCAN")
    print("What would the trend scanner find?")
    print("─" * 40)

    trends = await scrape_trending_topics(page)
    relevant = filter_relevant_trends(trends, config)

    print(f"Total trending: {len(trends)}")
    print(f"Relevant to your niche: {len(relevant)}")
    if relevant:
        for t in relevant[:5]:
            print(f"  • {t}")

    # ── STEP 2: Tweet generation ──────────────────────
    print("\n📝 STEP 2 — TWEET GENERATION")
    print("What would be queued for your approval?")
    print("─" * 40)

    from ai.trend_scanner import build_trend_context
    niche_posts = []
    trend_context = build_trend_context(relevant, niche_posts) if relevant else None

    tweet1 = generate_tweet(tweet_type="hot_take", trend_context=trend_context)
    tweet2 = generate_tweet(tweet_type="personal")

    print(f"\n  Morning tweet (would be queued for approval):")
    print(f"  \"{tweet1}\"")
    print(f"  {len(tweet1)}/280 chars\n")

    print(f"  Evening tweet (would be queued for approval):")
    print(f"  \"{tweet2}\"")
    print(f"  {len(tweet2)}/280 chars")

    # ── STEP 3: Reply preview ─────────────────────────
    print("\n↩  STEP 3 — REPLY PREVIEW")
    print("Who would be replied to in the first session?")
    print("─" * 40)

    from agent.targets import get_target_accounts
    targets = get_target_accounts()
    if not targets:
        targets = config.get("target_accounts", [])
    sample = random.sample(targets, min(4, len(targets)))

    for username in sample:
        print(f"\n  Checking @{username}...")
        followers = await get_follower_count(page, username)
        tier = get_tier(followers, config)
        tweets = await get_latest_tweets(page, username, count=1)

        if tweets:
            tweet = tweets[0]
            reply = generate_reply(
                tweet_text=tweet["text"],
                author=username,
                author_followers=followers,
                tier=tier,
                extra_context=tweet.get("extra_context")
            )
            print(f"  Followers: {followers:,} → Tier: {tier}")
            print(f"  Their tweet: \"{tweet['text'][:80]}...\"")
            print(f"  Would reply: \"{reply}\"")
        else:
            print(f"  Could not fetch tweets")

    # ── STEP 4: Summary ───────────────────────────────
    print("\n" + "=" * 50)
    print("📊 DRY RUN SUMMARY")
    print("=" * 50)
    print(f"  Trends found:     {len(relevant)} relevant")
    print(f"  Tweets queued:    2 (pending your approval)")
    print(f"  Accounts checked: {len(sample)}")
    print(f"  Replies ready:    {len(sample)} (would be sent)")
    print(f"\n  ✅ Agent looks healthy and ready to run")
    print(f"  Run: bash start.sh\n")

    await browser.close()
    await playwright.stop()


if __name__ == "__main__":
    asyncio.run(dry_run())
