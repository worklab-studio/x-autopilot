"""
scheduler.py — The brain that orchestrates everything
Runs actions on a human-like schedule throughout the day.
Enforces safety limits. Never runs at weird hours.
"""

import asyncio
import random
from pathlib import Path
from datetime import datetime, time, timedelta
from agent.dynamic_config import load_config_with_dynamic
from agent.autonomy import get_autonomy_profile, scale_count
from agent.humanize import dead_scroll_session, curiosity_profile_visit, weekend_scale_factor, is_weekend

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config():
    return load_config_with_dynamic(CONFIG_PATH)


def is_active_hours() -> bool:
    """Check if we're within the active hours window."""
    config = load_config()
    start_str = config["posting"]["active_hours_start"]  # e.g. "09:00"
    end_str = config["posting"]["active_hours_end"]       # e.g. "23:00"

    now = datetime.now().time()
    start = time(*map(int, start_str.split(":")))
    end = time(*map(int, end_str.split(":")))

    return start <= now <= end


def should_take_break() -> bool:
    """Randomly simulate the user stepping away (30% chance every hour)."""
    return random.random() < 0.3


def _minutes_until_active_end(config: dict, now: datetime = None) -> int:
    now = now or datetime.now()
    end_str = config["posting"]["active_hours_end"]
    end = time(*map(int, end_str.split(":")))
    end_dt = datetime.combine(now.date(), end)
    start_str = config["posting"].get("active_hours_start", "00:00")
    start = time(*map(int, start_str.split(":")))
    start_dt = datetime.combine(now.date(), start)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    if now >= end_dt:
        return 0
    return int((end_dt - now).total_seconds() // 60)


def _remaining_actions(config: dict) -> dict:
    from agent.logger import get_daily_count
    engagement = config.get("engagement", {})
    targets = {
        "reply": engagement.get("daily_replies", 0),
        "like": engagement.get("daily_likes", 0),
        "follow": engagement.get("daily_follows", 0),
        "dm": engagement.get("daily_dms", 0),
        "retweet": engagement.get("daily_retweets", 0),
    }
    remaining = {}
    for action, limit in targets.items():
        remaining[action] = max(0, int(limit) - get_daily_count(action))
    return remaining


async def _idle_scroll(page, scrolls: int = 2):
    from agent.browser import human_delay, human_scroll, human_navigate
    if not page:
        return
    try:
        if page.is_closed():
            return
        url = page.url or ""
        if "twitter.com" not in url and "x.com" not in url:
            await human_navigate(page, "https://x.com/home")
        for _ in range(max(1, scrolls)):
            await human_scroll(page)
            await human_delay(0.8, 1.6)
    except Exception:
        return


async def _poll_skip(set_status_fn, page=None) -> bool:
    """
    Check the skip-break flag. Returns True immediately if set.
    Checks both the file flag (written by the API) and the JS window variable
    (set directly by the overlay button), so skip works with or without Flask.
    """
    from agent.status_overlay import skip_break_requested, clear_skip_break_flag, check_skip_break_button
    triggered = skip_break_requested()
    if not triggered and page is not None:
        triggered = await check_skip_break_button(page)
    if triggered:
        clear_skip_break_flag()
        print("⏩  Break skipped by user.")
        await set_status_fn("⏩ Break skipped — starting next session")
        return True
    return False


async def _sleep_with_countdown(minutes: int, status_template: str, set_status_fn, page=None) -> bool:
    """
    Sleep for `minutes` with a visible countdown.
    Polls the skip-break flag every 3 seconds so the Skip button
    in the overlay takes effect almost instantly.
    Returns True if the sleep was cut short by the user (skip), False if it ran fully.
    """
    if minutes <= 0:
        return False

    total_secs = minutes * 60
    elapsed = 0.0
    POLL = 3  # check skip every 3 seconds

    # Show initial status immediately
    await set_status_fn(status_template.format(mins=minutes))

    while elapsed < total_secs:
        if await _poll_skip(set_status_fn, page):
            return True  # skipped early

        chunk = min(POLL, total_secs - elapsed)
        await asyncio.sleep(chunk)
        elapsed += chunk

        displayed_mins = max(1, int((total_secs - elapsed + 59) / 60))
        await set_status_fn(status_template.format(mins=displayed_mins))

    return False  # completed normally


async def _sleep_with_idle_scroll(page, minutes: int, status_template: str, set_status_fn, config: dict, allow_scroll: bool = True) -> bool:
    """
    Sleep for `minutes` with optional idle scrolling.
    Polls the skip-break flag every 3 seconds so the Skip button
    in the overlay takes effect almost instantly.
    Returns True if the sleep was cut short by the user (skip), False if it ran fully.
    """
    if minutes <= 0:
        return False

    safety = config.get("safety", {}) if config else {}
    scroll_enabled = bool(safety.get("idle_scroll_enabled", False)) and allow_scroll
    scroll_interval_secs = int(safety.get("idle_scroll_interval_minutes", 8) or 8) * 60
    scrolls = int(safety.get("idle_scroll_scrolls", 2) or 2)
    scroll_interval_secs = max(30, scroll_interval_secs)

    total_secs = minutes * 60
    elapsed = 0.0
    since_scroll = 0.0
    POLL = 3  # check skip every 3 seconds

    # Show initial status immediately
    await set_status_fn(status_template.format(mins=minutes))

    while elapsed < total_secs:
        if await _poll_skip(set_status_fn, page):
            return True  # skipped early

        chunk = min(POLL, total_secs - elapsed)
        await asyncio.sleep(chunk)
        elapsed += chunk
        since_scroll += chunk

        # Idle scroll if due
        if scroll_enabled and since_scroll >= scroll_interval_secs:
            await set_status_fn("Idle scrolling feed…")
            await _idle_scroll(page, scrolls=scrolls)
            since_scroll = 0.0

        # Update countdown display
        displayed_mins = max(1, int((total_secs - elapsed + 59) / 60))
        await set_status_fn(status_template.format(mins=displayed_mins))

    return False  # completed normally


async def _no_queue_discovery(page, config: dict, profile: dict):
    from actions.reply import run_reply_session
    from actions.like import like_from_feed
    from agent.status_overlay import set_status

    reply_max = 4
    like_max = 6
    home_max = 3
    hashtag_max = 2

    if profile and profile.get("enabled"):
        volume = profile.get("volume_factor", 1.0)
        reply_max = scale_count(reply_max, volume)
        # Shift ratios to favor home page over hashtags
        home_ratio = float(profile.get("home_reply_ratio", 0.40))
        hashtag_ratio = float(profile.get("hashtag_reply_ratio", 0.15))
        home_max = max(0, int(round(reply_max * home_ratio)))
        hashtag_max = max(0, int(round(reply_max * hashtag_ratio)))
        if home_max + hashtag_max == 0 and reply_max > 0:
            home_max = reply_max
        like_factor = volume * (profile.get("home_like_ratio", 0.3) / 0.3)
        like_max = scale_count(like_max, like_factor)

    if reply_max <= 0 and like_max <= 0:
        return

    await set_status("No approved tweets — scanning home/hashtags")
    await run_reply_session(
        page,
        max_replies=reply_max,
        target_limit=0,
        max_hashtag_replies_override=hashtag_max,
        max_home_replies_override=home_max,
    )
    await like_from_feed(page, max_likes=like_max)


def _is_turbo() -> bool:
    """Turbo mode: skip all long sleeps for demos/recordings."""
    return bool(load_config().get("turbo_mode", False))


async def _between_action_sleep():
    """Sleep between actions — 4–10s in turbo mode, 60–180s normally."""
    if _is_turbo():
        await asyncio.sleep(random.uniform(4, 10))
    else:
        await asyncio.sleep(random.uniform(60, 180))


async def _run_action_sequence(actions: list, profile: dict, nav_limit: int = None):
    action_list = [(name, fn, nav_heavy) for name, fn, nav_heavy in actions if fn is not None]
    if not action_list:
        return
    # Always shuffle the action list so real human sessions aren't predictable pipelines
    random.shuffle(action_list)
    nav_used = 0
    for index, (_, fn, nav_heavy) in enumerate(action_list):
        if nav_limit is not None and nav_heavy and nav_used >= nav_limit:
            continue
        await fn()
        if nav_heavy:
            nav_used += 1
        if index < len(action_list) - 1:
            await _between_action_sleep()


async def morning_session(page):
    """9am - 12pm: Heavy engagement, trend scan, first tweet generation."""
    from actions.reply import run_reply_session
    from actions.like import like_from_feed, like_from_profiles
    from actions.follow import run_follow_session
    from actions.tweet import generate_and_queue_tweet, generate_and_queue_promo_tweet, post_approved_tweets
    from actions.notifications import run_notifications_session
    from ai.trend_scanner import generate_trend_based_tweet, generate_weekly_thread

    from agent.status_overlay import set_status
    print("\n🌅 MORNING SESSION")
    await set_status("Morning session: starting")
    config = load_config()
    profile = get_autonomy_profile(config)
    nav_limit = int(config.get("safety", {}).get("nav_actions_per_session", 2) or 0)

    if config.get("posting", {}).get("auto_generate_threads", False):
        print("📅 Daily thread — generating deep-dive...")
        await set_status("Generating daily thread")
        await generate_weekly_thread(page)

    if config.get("posting", {}).get("auto_generate_tweets", False):
        await generate_trend_based_tweet(page)

    if config.get("posting", {}).get("auto_generate_promos", False):
        await generate_and_queue_promo_tweet(load_config())

    if not _is_turbo():
        await asyncio.sleep(random.uniform(30, 90))

    # Post any approved tweets
    await set_status("Posting approved tweets")
    post_result = await post_approved_tweets(page)
    if post_result == "empty":
        await set_status("No approved tweets")
        await _no_queue_discovery(page, config, profile)
    elif post_result == "limit":
        await set_status("Tweet limit reached")
    await _between_action_sleep()

    reply_max = 8
    like_max = 12
    follow_max = 8
    target_limit = None
    max_hashtag = None
    max_home = None
    if profile.get("enabled"):
        volume = profile["volume_factor"]
        reply_max = scale_count(reply_max, volume)
        target_limit = max(0, int(round(reply_max * profile.get("target_reply_ratio", 0.45))))
        max_hashtag = max(0, int(round(reply_max * profile.get("hashtag_reply_ratio", 0.15))))
        max_home = max(0, reply_max - target_limit - max_hashtag)
        like_factor = volume * (profile.get("home_like_ratio", 0.3) / 0.3)
        follow_factor = volume * (profile.get("follow_ratio", 0.3) / 0.3)
        like_max = scale_count(like_max, like_factor)
        follow_max = scale_count(follow_max, follow_factor)

    # Quieter on weekends
    wk = weekend_scale_factor()
    reply_max = max(1, int(reply_max * wk))
    like_max = max(1, int(like_max * wk))
    follow_max = max(1, int(follow_max * wk))

    actions = [
        ("notifications", lambda: run_notifications_session(page), True),
        ("replies", lambda: run_reply_session(
            page,
            max_replies=reply_max,
            target_limit=target_limit,
            max_hashtag_replies_override=max_hashtag,
            max_home_replies_override=max_home,
        ), False),
        ("likes", lambda: like_from_feed(page, max_likes=like_max), False),
        ("profile_likes", lambda: like_from_profiles(page), True),
        ("follows", lambda: run_follow_session(page, max_follows=follow_max), True),
    ]
    await _run_action_sequence(actions, profile, nav_limit=nav_limit)


async def afternoon_session(page):
    """1pm - 5pm: DMs, more replies, unfollow cleanup."""
    from actions.reply import run_reply_session
    from actions.dm import run_dm_session, check_dm_replies
    from actions.follow import run_unfollow_session
    from actions.tweet import generate_and_queue_promo_tweet, post_approved_tweets
    from actions.notifications import run_notifications_session

    from agent.status_overlay import set_status
    print("\n☀️  AFTERNOON SESSION")
    await set_status("Afternoon session: starting")
    config = load_config()
    profile = get_autonomy_profile(config)
    nav_limit = int(config.get("safety", {}).get("nav_actions_per_session", 2) or 0)

    async def _do_check_dms():
        await set_status("Checking DMs")
        await check_dm_replies(page)

    reply_max = 8
    target_limit = None
    max_hashtag = None
    max_home = None
    if profile.get("enabled"):
        volume = profile["volume_factor"]
        reply_max = scale_count(reply_max, volume)
        target_limit = max(0, int(round(reply_max * profile.get("target_reply_ratio", 0.45))))
        max_hashtag = max(0, int(round(reply_max * profile.get("hashtag_reply_ratio", 0.15))))
        max_home = max(0, reply_max - target_limit - max_hashtag)

    wk = weekend_scale_factor()
    reply_max = max(1, int(reply_max * wk))

    actions = [
        ("check_dms", _do_check_dms, True),
        ("notifications", lambda: run_notifications_session(page), True),
        ("dm_session", lambda: run_dm_session(page), True),
        ("replies", lambda: run_reply_session(
            page,
            max_replies=reply_max,
            target_limit=target_limit,
            max_hashtag_replies_override=max_hashtag,
            max_home_replies_override=max_home,
        ), False),
        ("post_tweets", lambda: post_approved_tweets(page), False),
        ("promo", lambda: generate_and_queue_promo_tweet(load_config()), False),
        ("unfollow", lambda: run_unfollow_session(page, max_unfollows=10), True),
    ]
    if not config.get("posting", {}).get("auto_generate_promos", False):
        actions = [item for item in actions if item[0] != "promo"]
    await _run_action_sequence(actions, profile, nav_limit=nav_limit)


async def evening_session(page):
    """6pm - 11pm: Second tweet, engagement, wrap up."""
    from actions.reply import run_reply_session
    from actions.like import like_from_feed, like_from_profiles
    from actions.tweet import generate_and_queue_tweet, generate_and_queue_promo_tweet, post_approved_tweets
    from actions.follow import run_follow_session
    from actions.notifications import run_notifications_session

    from agent.status_overlay import set_status
    print("\n🌆 EVENING SESSION")
    await set_status("Evening session: starting")
    config = load_config()
    profile = get_autonomy_profile(config)
    nav_limit = int(config.get("safety", {}).get("nav_actions_per_session", 2) or 0)

    if config.get("posting", {}).get("auto_generate_tweets", False):
        await set_status("Generating evening tweet")
        await generate_and_queue_tweet(tweet_type="personal")
        await _between_action_sleep()

    if config.get("posting", {}).get("auto_generate_promos", False):
        await set_status("Queueing promo tweet")
        await generate_and_queue_promo_tweet(load_config())

    # Post approved tweets
    await set_status("Posting approved tweets")
    post_result = await post_approved_tweets(page)
    if post_result == "empty":
        await set_status("No approved tweets")
        await _no_queue_discovery(page, config, profile)
    elif post_result == "limit":
        await set_status("Tweet limit reached")
    if not _is_turbo():
        await asyncio.sleep(random.uniform(120, 300))

    reply_max = 10
    like_max = 10
    follow_max = 8
    target_limit = None
    max_hashtag = None
    max_home = None
    if profile.get("enabled"):
        volume = profile["volume_factor"]
        reply_max = scale_count(reply_max, volume)
        target_limit = max(0, int(round(reply_max * profile.get("target_reply_ratio", 0.45))))
        max_hashtag = max(0, int(round(reply_max * profile.get("hashtag_reply_ratio", 0.15))))
        max_home = max(0, reply_max - target_limit - max_hashtag)
        like_factor = volume * (profile.get("home_like_ratio", 0.3) / 0.3)
        follow_factor = volume * (profile.get("follow_ratio", 0.3) / 0.3)
        like_max = scale_count(like_max, like_factor)
        follow_max = scale_count(follow_max, follow_factor)

    wk = weekend_scale_factor()
    reply_max = max(1, int(reply_max * wk))
    like_max = max(1, int(like_max * wk))
    follow_max = max(1, int(follow_max * wk))

    actions = [
        ("notifications", lambda: run_notifications_session(page), True),
        ("replies", lambda: run_reply_session(
            page,
            max_replies=reply_max,
            target_limit=target_limit,
            max_hashtag_replies_override=max_hashtag,
            max_home_replies_override=max_home,
        ), False),
        ("likes", lambda: like_from_feed(page, max_likes=like_max), False),
        ("profile_likes", lambda: like_from_profiles(page), True),
        ("follows", lambda: run_follow_session(page, max_follows=follow_max), True),
    ]
    await _run_action_sequence(actions, profile, nav_limit=nav_limit)


async def save_growth_snapshot(page):
    """Once a day, save the follower count for the growth graph."""
    from agent.logger import save_growth_snapshot as _save
    from agent.browser import human_navigate

    try:
        from dotenv import load_dotenv
        import os
        load_dotenv()
        username = os.getenv("TWITTER_USERNAME", "")

        await human_navigate(page, f"https://x.com/{username}")
        await asyncio.sleep(3)

        # Get follower count
        followers_el = await page.query_selector(f'[href="/{username}/followers"] span span')
        following_el = await page.query_selector(f'[href="/{username}/following"] span span')

        followers = 0
        following = 0

        if followers_el:
            from actions.reply import _parse_follower_count
            text = await followers_el.inner_text()
            followers = _parse_follower_count(text)

        if following_el:
            from actions.reply import _parse_follower_count
            text = await following_el.inner_text()
            following = _parse_follower_count(text)

        _save(followers=followers, following=following, tweets=0)
        print(f"📊 Growth snapshot: {followers} followers, {following} following")

    except Exception as e:
        print(f"⚠️  Could not save growth snapshot: {e}")


async def run_scheduler(page):
    """
    Main scheduler loop — runs all day.
    Determines which session to run based on time of day.
    """
    from agent.status_overlay import set_status
    print("\n⏰ SCHEDULER STARTED")
    print("Agent will run human-like sessions throughout the day.\n")
    await set_status("Scheduler started")

    snapshot_saved_today = False
    skip_next_break = False  # set True when user skips a sleep so we jump straight to next session

    while True:
        # Check if paused from dashboard
        state_file = Path(__file__).parent.parent / "data" / "agent_state.json"
        if state_file.exists():
            import json
            with open(state_file) as f:
                state = json.load(f)
            if state.get("paused"):
                print("⏸  Agent paused from dashboard. Waiting...")
                await set_status("Paused from dashboard")
                await asyncio.sleep(30)
                continue

        config = load_config()
        if not is_active_hours():
            print("😴 Outside active hours — agent sleeping...")
            await set_status("Sleeping (outside active hours)")
            await asyncio.sleep(30 if _is_turbo() else 300)  # turbo: 30s, normal: 5 mins
            continue

        now = datetime.now()
        hour = now.hour
        minutes_left = _minutes_until_active_end(config, now)
        remaining = _remaining_actions(config)
        catch_up = minutes_left <= 60 and sum(remaining.values()) > 0
        if catch_up:
            await set_status("Catch-up mode: using remaining limits")

        # Save growth snapshot at 8am and 6pm to keep today's count fresh
        if hour in (8, 18) and not snapshot_saved_today:
            await save_growth_snapshot(page)
            snapshot_saved_today = True

        # Reset daily snapshot flag at midnight and at 9am (so 6pm can fire again)
        if hour == 0 or hour == 9:
            snapshot_saved_today = False

        # ── Weekend behaviour: reduce action quotas ─────────────────────────
        wk_scale = weekend_scale_factor()
        if wk_scale < 1.0:
            day_name = "Saturday" if datetime.now().weekday() == 5 else "Sunday"
            print(f"📅 {day_name} — scaling activity to {int(wk_scale*100)}% of normal")
            await set_status(f"{day_name} mode ({int(wk_scale*100)}% activity)")

        turbo = _is_turbo()

        # ── If the user just skipped a break/sleep, go straight to the session ──
        if skip_next_break:
            skip_next_break = False
            # Fall through directly to the session block below
        elif turbo:
            pass  # turbo mode: skip all dead-scroll, curiosity, and break rolls
        else:
            # ── 20% chance: dead scroll instead of real session ──────────────────
            if random.random() < 0.20 and not catch_up:
                await dead_scroll_session(page)
                # Also optionally do a curiosity visit after browsing
                if random.random() < 0.40:
                    await curiosity_profile_visit(page)
                wait_mins = random.randint(60, 120)
                was_skipped = await _sleep_with_idle_scroll(page, wait_mins, "Idle after browsing ({mins} min)", set_status, config)
                if was_skipped:
                    skip_next_break = True  # bypass break roll on the next pass
                continue  # regardless, loop back (skip_next_break will short-circuit rolls next time)

            # ── 15% chance: curiosity profile visit before main session ──────────
            if random.random() < 0.15 and not catch_up:
                await curiosity_profile_visit(page)
                await asyncio.sleep(random.uniform(30, 90))

            # ── Random break simulation ──────────────────────────────────────────
            break_chance = 0.20 if is_weekend() else 0.30
            if random.random() < break_chance and not catch_up:
                break_mins = random.randint(20, 60)
                print(f"☕ Taking a {break_mins} minute break (simulating human)...")
                was_skipped = await _sleep_with_countdown(break_mins, "Taking a break (~{mins} min)", set_status, page=page)
                if not was_skipped:
                    continue  # normal end of break — loop back for next session decision
                # if skipped, fall through immediately to run a session now

        # Determine session dynamically to avoid hard-gated 4-hour blocks
        try:
            active_sessions = [morning_session, afternoon_session, evening_session]

            if hour < 12:
                session_func = random.choices(active_sessions, weights=[85, 15, 0])[0]
            elif 12 <= hour < 17:
                session_func = random.choices(active_sessions, weights=[15, 70, 15])[0]
            else:
                session_func = random.choices(active_sessions, weights=[0, 15, 85])[0]

            await session_func(page)

        except Exception as e:
            print(f"⚠️  Session error: {e}")
            await set_status("Session error — retrying soon")
            await asyncio.sleep(15 if _is_turbo() else 300)

        # Wait between sessions
        if turbo:
            print(f"\n⚡ Turbo mode — firing next session immediately...")
            await set_status("⚡ Turbo: loading next session...")
            await asyncio.sleep(3)
        elif catch_up:
            wait_mins = random.randint(6, 15)
            print(f"\n⏳ Catch-up wait ~{wait_mins} minutes...")
            await _sleep_with_idle_scroll(page, wait_mins, "Catch-up idle (~{mins} min)", set_status, config)
        else:
            # Sleep 2-3 hours before next session
            wait_mins = random.randint(120, 180)
            print(f"\n⏳ Next session in ~{wait_mins} minutes...")
            was_skipped = await _sleep_with_idle_scroll(page, wait_mins, "Sleeping {mins} min until next session", set_status, config)
            if was_skipped:
                skip_next_break = True  # next loop: skip random rolls, go straight to session
