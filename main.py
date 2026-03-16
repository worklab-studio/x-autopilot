"""
main.py — Twitter Agent Entry Point
Run this file to start the agent.

Usage:
  python main.py              # Start full agent
  python main.py --test       # Test session only (no actions)
  python main.py --dashboard  # Start dashboard only
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


async def run_agent():
    """Start the full Twitter agent."""
    print("""
╔══════════════════════════════════════╗
║       TWITTER GROWTH AGENT          ║
║       Starting up...                ║
╚══════════════════════════════════════╝
    """)

    from agent.browser import launch_browser, get_page
    from agent.session import ensure_logged_in
    from agent.logger import get_today_stats
    from agent.status_overlay import (
        register_page, set_status,
        clear_quit_flag, check_quit_button,
    )

    # Clear any stale quit flag from a previous unclean exit
    clear_quit_flag()

    # Launch browser
    print("🚀 Launching browser...")
    playwright, browser = await launch_browser(headless=False)
    page = await get_page(browser)
    register_page(page)
    await set_status("Starting agent…")

    # Ensure logged in
    logged_in = await ensure_logged_in(browser, page)
    if not logged_in:
        print("❌ Failed to log in. Exiting.")
        await browser.close()
        await playwright.stop()
        return

    print("\n✅ Agent is live. Dashboard: http://localhost:5000\n")
    print("Today's stats:", get_today_stats())
    print("\nAgent is running… Click ✕ Quit in the browser overlay or press Ctrl+C to stop.\n")
    await set_status("Agent live — scheduler running")

    # Take an immediate follower snapshot so the growth chart shows real data from day 1
    from agent.scheduler import save_growth_snapshot, run_scheduler
    await save_growth_snapshot(page)

    # Run scheduler as a background task so we can poll for quit
    scheduler_task = asyncio.ensure_future(run_scheduler(page))

    async def _quit_watcher():
        """Poll every 5s for the overlay Quit button press."""
        while not scheduler_task.done():
            await asyncio.sleep(5)
            if await check_quit_button(page):
                print("\n🛑 Quit button pressed — stopping agent cleanly…")
                scheduler_task.cancel()
                return

    watcher_task = asyncio.ensure_future(_quit_watcher())

    try:
        await scheduler_task
    except asyncio.CancelledError:
        print("⏹  Scheduler cancelled.")
    except KeyboardInterrupt:
        print("\n⏹  Agent stopped by user (Ctrl+C).")
        scheduler_task.cancel()
    finally:
        watcher_task.cancel()
        try:
            await set_status("Agent stopped")
            await asyncio.sleep(0.5)
        except Exception:
            pass
        await browser.close()
        await playwright.stop()
        clear_quit_flag()
        print("✅ Browser closed. Session saved.")



async def test_session():
    """Test that session loading works."""
    from agent.session import test_session as _test
    await _test()


def run_dashboard():
    """Start the dashboard server."""
    print("🖥  Starting dashboard at http://localhost:5000")
    # Dashboard server will be built in Session 5
    print("⚠️  Dashboard not yet built — coming in Session 5")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Twitter Growth Agent")
    parser.add_argument("--test", action="store_true", help="Test session only")
    parser.add_argument("--dashboard", action="store_true", help="Start dashboard only")
    args = parser.parse_args()

    if args.test:
        asyncio.run(test_session())
    elif args.dashboard:
        run_dashboard()
    else:
        asyncio.run(run_agent())
