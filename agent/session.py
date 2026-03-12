"""
session.py — Twitter login & session management
Handles logging in once, saving cookies, and staying logged in.
You'll only need to manually log in ONE time. After that it's automatic.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from agent.browser import launch_browser, get_page, human_delay, human_type
from dotenv import load_dotenv
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

load_dotenv()

COOKIES_FILE = Path(__file__).parent.parent / "data" / "twitter_cookies.json"
TWITTER_HOME = "https://x.com/home"
TWITTER_LOGIN = "https://x.com/i/flow/login"


async def is_logged_in(page) -> bool:
    """Check if we're currently logged in to Twitter."""
    try:
        await page.goto(TWITTER_HOME, wait_until="domcontentloaded", timeout=15000)
        await human_delay(2, 4)

        # If we're redirected to login page, we're not logged in
        current_url = page.url
        if "login" in current_url or "i/flow" in current_url:
            return False

        # Check for the home timeline element
        timeline = await page.query_selector('[data-testid="primaryColumn"]')
        return timeline is not None

    except Exception as e:
        print(f"⚠️  Login check failed: {e}")
        return False


async def manual_login(browser, page):
    """
    Opens Twitter login page and waits for YOU to log in manually.
    This only needs to happen once — session is saved after.
    """
    print("\n" + "="*50)
    print("🔐 MANUAL LOGIN REQUIRED")
    print("="*50)
    print("The browser will open Twitter's login page.")
    print("Please log in manually in the browser window.")
    print("Once you're on your home feed, come back here and press ENTER.")
    print("="*50 + "\n")

    await page.goto(TWITTER_LOGIN, wait_until="domcontentloaded")
    await human_delay(2, 3)

    is_tty = sys.stdin is not None and sys.stdin.isatty()
    if is_tty:
        try:
            # Wait for user to complete login
            input("👆 Log in to Twitter in the browser, then press ENTER here...")
        except EOFError:
            is_tty = False

    if not is_tty:
        timeout_seconds = int(os.getenv("TWITTER_LOGIN_TIMEOUT", "600"))
        print(f"👀 Waiting up to {timeout_seconds}s for login to complete...")
        try:
            await page.wait_for_url("**/home*", timeout=timeout_seconds * 1000)
            await page.wait_for_selector('[data-testid="primaryColumn"]', timeout=30000)
        except PlaywrightTimeoutError:
            print("❌ Login timed out. Please try again.")
            return False

    # Verify login worked
    logged_in = await is_logged_in(page)
    if logged_in:
        await save_session(browser)
        print("✅ Login successful! Session saved — won't need to do this again.")
        return True
    else:
        print("❌ Login failed. Please try again.")
        return False


async def save_session(browser):
    """Save cookies and storage so we stay logged in."""
    cookies = await browser.cookies()
    COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"💾 Session saved to {COOKIES_FILE}")


async def load_session(browser):
    """Load saved cookies to restore login session."""
    if not COOKIES_FILE.exists():
        print("📂 No saved session found — manual login required.")
        return False

    try:
        with open(COOKIES_FILE, "r") as f:
            cookies = json.load(f)
        await browser.add_cookies(cookies)
        print("🔄 Session cookies loaded.")
        return True
    except Exception as e:
        print(f"⚠️  Failed to load session: {e}")
        return False


async def ensure_logged_in(browser, page) -> bool:
    """
    Main function — call this before any action.
    Automatically handles login or session restore.
    """
    # Try loading saved session first
    session_loaded = await load_session(browser)

    if session_loaded:
        # Check if session is still valid
        logged_in = await is_logged_in(page)
        if logged_in:
            username = os.getenv("TWITTER_USERNAME", "your account")
            print(f"✅ Already logged in as @{username}")
            return True
        else:
            print("⚠️  Saved session expired — need to log in again.")

    # Session not valid — need manual login
    return await manual_login(browser, page)


async def refresh_if_needed(page):
    """Refresh the page if Twitter shows an error or goes stale."""
    try:
        error = await page.query_selector('[data-testid="error-detail"]')
        if error:
            print("🔄 Refreshing page after error...")
            await page.reload(wait_until="domcontentloaded")
            await human_delay(2, 4)
    except Exception:
        pass


# ─────────────────────────────────────────
# STANDALONE TEST — run this file directly
# to verify your session is working
# ─────────────────────────────────────────
async def test_session():
    playwright, browser = await launch_browser(headless=False)
    page = await get_page(browser)

    success = await ensure_logged_in(browser, page)

    if success:
        print("\n✅ SESSION TEST PASSED")
        print("Twitter is open and you're logged in.")
        print("The agent is ready to use your account.")
        await asyncio.sleep(5)
    else:
        print("\n❌ SESSION TEST FAILED")
        print("Please check your credentials and try again.")

    await browser.close()
    await playwright.stop()


if __name__ == "__main__":
    asyncio.run(test_session())
