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


def _clear_chrome_profile():
    """Delete the Chrome profile directory so the next launch starts fresh."""
    import shutil
    profile_dir = Path(__file__).parent.parent / "data" / "chrome_profile"
    cookies_file = Path(__file__).parent.parent / "data" / "twitter_cookies.json"
    try:
        if profile_dir.exists():
            shutil.rmtree(profile_dir)
        cookies_file.unlink(missing_ok=True)
        print("🗑  Chrome profile cleared — will log in fresh on next start.")
    except Exception as e:
        print(f"⚠️  Could not clear Chrome profile: {e}")


async def is_logged_in(page) -> bool:
    """Check if we're currently logged in to Twitter."""
    try:
        current_url = page.url or ""
        already_on_home = "x.com/home" in current_url or "twitter.com/home" in current_url

        if not already_on_home:
            await page.goto(TWITTER_HOME, wait_until="domcontentloaded", timeout=20000)
            # Always use a fixed 3s wait here — turbo mode shrinks human_delay
            # but login detection needs real page load time regardless of mode
            await asyncio.sleep(3)
            current_url = page.url
        else:
            # Already on home — just give React a moment to settle
            await asyncio.sleep(2)

        # If we're redirected to login page, we're not logged in
        if "login" in current_url or "i/flow" in current_url:
            return False

        # Detect stuck X-logo loading screen: page stays on x.com but
        # primaryColumn never appears. This happens when the Chrome profile
        # is corrupted — React hydration loops forever.
        try:
            await page.wait_for_selector('[data-testid="primaryColumn"]', timeout=10000)
            return True
        except PlaywrightTimeoutError:
            # Check if we're stuck on the X logo splash screen
            try:
                url = page.url or ""
                body_text = await page.evaluate("document.body ? document.body.innerText : ''")
                if "x.com" in url and len(body_text.strip()) < 50:
                    print("⚠️  Browser stuck on X loading screen — Chrome profile is likely corrupted.")
                    print("   Clearing profile so the next run starts with a clean browser...")
                    _clear_chrome_profile()
                    # Navigate away to break the JS loop so subsequent gotos work
                    try:
                        await page.goto("about:blank", wait_until="domcontentloaded", timeout=5000)
                    except Exception:
                        pass
            except Exception:
                pass
            return False

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
    print("")
    print("  Log in to Twitter in the browser window.")
    print("  You can use email/password, Google, or Apple.")
    print("")
    print("  Once you're on your home feed, press ENTER here.")
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
    # Clear Chrome's session restore — navigate to blank to break any stuck state
    # (Chrome may have restored x.com/home from last session, causing a React hydration loop)
    try:
        await page.goto("about:blank", wait_until="domcontentloaded", timeout=8000)
        await asyncio.sleep(0.5)
    except Exception:
        pass

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
