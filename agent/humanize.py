"""
humanize.py — Human-like behaviour helpers.
"""

import asyncio
import random
from datetime import datetime

from agent.status_overlay import set_status


async def maybe_micro_break(
    label: str = "Short break",
    chance: float = 0.08,
    min_seconds: float = 6.0,
    max_seconds: float = 18.0,
) -> None:
    if random.random() >= chance:
        return
    try:
        await set_status(label)
    except Exception:
        pass
    await asyncio.sleep(random.uniform(min_seconds, max_seconds))


# ── Weekend scaling ───────────────────────────────────────────────────────────

def is_weekend() -> bool:
    """Return True if today is Saturday (5) or Sunday (6)."""
    return datetime.now().weekday() >= 5


def weekend_scale_factor() -> float:
    """
    Return a multiplier for action counts on weekends.
    Humans are less active on weekends — fewer replies, more passive browsing.
    Saturday → 0.55,  Sunday → 0.40  (random within a narrow band).
    """
    if not is_weekend():
        return 1.0
    day = datetime.now().weekday()
    if day == 5:   # Saturday — a bit active
        return random.uniform(0.45, 0.65)
    return random.uniform(0.30, 0.50)  # Sunday — very lazy


# ── Dead scrolling session ────────────────────────────────────────────────────

async def dead_scroll_session(page, min_scrolls: int = 6, max_scrolls: int = 18) -> None:
    """
    Scroll through the feed without engaging with anything.
    Simulates a human who opens Twitter, browses passively, then leaves.
    Called ~20% of the time from the scheduler instead of a real session.
    """
    from agent.browser import human_scroll, human_delay, human_navigate

    n = random.randint(min_scrolls, max_scrolls)
    print(f"📜 Dead scroll session — just browsing ({n} scrolls, no engagement)")
    try:
        await set_status("Browsing feed (no engagement)")
    except Exception:
        pass

    try:
        url = page.url or ""
        if "twitter.com" not in url and "x.com" not in url:
            await human_navigate(page, "https://x.com/home")

        for _ in range(n):
            await human_scroll(page, amount=random.randint(250, 700))
            # Linger on content sometimes
            await human_delay(random.uniform(0.8, 4.5))
            # Occasional long read pause (someone reading a thread)
            if random.random() < 0.15:
                await asyncio.sleep(random.uniform(8, 22))

    except Exception:
        pass

    print("📜 Dead scroll complete — moving on")


# ── Curiosity profile visits ──────────────────────────────────────────────────

async def curiosity_profile_visit(page, candidates: list = None) -> None:
    """
    Visit 1-3 profiles out of pure curiosity, scroll a bit, then leave without
    doing anything. Mirrors how humans click on a name they see and bounce.

    `candidates` is an optional list of Twitter usernames to visit.
    If empty, navigates to the home feed and picks names from UserCell elements.
    """
    from agent.browser import human_scroll, human_delay, human_click, human_navigate

    try:
        await set_status("Browsing profiles out of curiosity")
    except Exception:
        pass

    visit_count = random.randint(1, 3)

    # Resolve candidates from feed if none provided
    if not candidates:
        try:
            await human_navigate(page, "https://x.com/home")
            cells = await page.query_selector_all('[data-testid="tweet"]')
            _names = []
            for cell in cells[:20]:
                try:
                    link = await cell.query_selector('a[href^="/"][href*="/status/"]')
                    if link:
                        href = await link.get_attribute("href")
                        if href:
                            username = href.split("/")[1]
                            if username and username not in _names:
                                _names.append(username)
                except Exception:
                    continue
            candidates = _names
        except Exception:
            return

    if not candidates:
        return

    chosen = random.sample(candidates, min(visit_count, len(candidates)))

    for username in chosen:
        try:
            print(f"👀 Curiosity visit: @{username} (no engagement planned)")
            await human_navigate(page, f"https://x.com/{username}")

            # Scroll through a bit — like a human reading a profile
            scrolls = random.randint(2, 5)
            for _ in range(scrolls):
                await human_scroll(page, amount=random.randint(200, 500))
                await human_delay(1.5, 5)

            # 20% chance of clicking into a tweet to read it, then going back
            if random.random() < 0.2:
                tweets = await page.query_selector_all('[data-testid="tweet"]')
                if tweets:
                    chosen_tweet = random.choice(tweets[:5])
                    await human_click(page, chosen_tweet)
                    await human_delay(4, 12)
                    await page.go_back()
                    await human_delay(1.5, 3)

            await human_delay(1, 3)

        except Exception:
            continue

    print(f"👀 Curiosity visits done ({len(chosen)} profiles)")

