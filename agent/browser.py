"""
browser.py — Stealth Chrome launcher
Runs a real visible Chrome browser that looks exactly like a human.
Twitter cannot detect this as automation.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from dotenv import load_dotenv
import random
from agent.fingerprint import FINGERPRINT_SCRIPT, SESSION_PROFILE

load_dotenv()

# Where your Chrome user data (cookies, session) will be saved
USER_DATA_DIR = Path(__file__).parent.parent / "data" / "chrome_profile"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)


async def launch_browser(headless: bool = False):
    """
    Launch a stealth Chrome browser.
    headless=False means you SEE the browser window (recommended).
    headless=True means it runs invisibly in background.
    """
    playwright = await async_playwright().start()

    browser = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=headless,
        channel="chrome",  # Use real Chrome, not Chromium
        # Prefer native browser defaults to avoid forced fingerprint mismatches.
        no_viewport=True,
    )

    if not headless:
        auto_focus = os.getenv("CHROME_AUTO_FOCUS", "1").lower() in {"1", "true", "yes", "on"}
        if auto_focus and sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e", 'tell application "Google Chrome" to activate'],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    # Make the Playwright cursor visible for the user
    _CURSOR_JS = """
    if (window !== window.parent) return; // Only top level
    const box = document.createElement('div');
    Object.assign(box.style, {
        position: 'fixed',
        top: 0,
        left: 0,
        width: '16px',
        height: '16px',
        background: 'rgba(239, 68, 68, 0.65)',
        border: '2px solid rgba(255, 255, 255, 0.8)',
        borderRadius: '50%',
        pointerEvents: 'none',
        zIndex: '2147483647',
        transform: 'translate(-50%, -50%)',
        transition: 'width 0.1s, height 0.1s, background 0.1s',
        display: 'none'
    });
    document.addEventListener('DOMContentLoaded', () => document.documentElement.appendChild(box));

    document.addEventListener('mousemove', event => {
        box.style.display = 'block';
        box.style.left = event.clientX + 'px';
        box.style.top = event.clientY + 'px';
    }, true);

    document.addEventListener('mousedown', () => {
        box.style.background = 'rgba(22, 163, 74, 0.85)'; // Green on click
        box.style.width = '12px';
        box.style.height = '12px';
    }, true);

    document.addEventListener('mouseup', () => {
        box.style.background = 'rgba(239, 68, 68, 0.65)'; // Back to red
        box.style.width = '16px';
        box.style.height = '16px';
    }, true);
    """

    # Apply stealth patches + deep fingerprint spoofing + visible cursor to every new page
    async def _setup_page(page):
        await stealth_async(page)
        await page.add_init_script(FINGERPRINT_SCRIPT)
        await page.add_init_script(_CURSOR_JS)

    browser.on("page", lambda page: asyncio.ensure_future(_setup_page(page)))

    # Stealth the existing pages too
    for page in browser.pages:
        await stealth_async(page)
        await page.add_init_script(FINGERPRINT_SCRIPT)
        try:
            await page.evaluate(_CURSOR_JS)
        except Exception:
            pass

    profile = SESSION_PROFILE
    print(f"✅ Stealth browser launched — profile: {profile['platform']}, "
          f"{profile['hardwareConcurrency']}×CPU, {profile['deviceMemory']}GB RAM, "
          f"GPU: {profile['renderer'].split('(')[1].split(',')[0] if '(' in profile['renderer'] else 'unknown'}")
    return playwright, browser


async def get_page(browser):
    """Get the current active page or open a new one."""
    pages = browser.pages
    if pages:
        return pages[0]
    return await browser.new_page()


async def close_browser(playwright, browser):
    """Cleanly close browser and save session."""
    await browser.close()
    await playwright.stop()
    print("🛑 Browser closed. Session saved.")


async def human_delay(min_seconds: float = 1.5, max_seconds: float = 4.5):
    """
    Wait a random human-like amount of time.
    Never use fixed delays — they're a bot fingerprint.
    """
    delay = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(delay)


async def human_click(page, element):
    """
    Move the cursor visibly to the element before clicking.
    Real humans don't instantly click without moving the mouse!
    """
    if not element:
        return
        
    try:
        # Give a small natural pause before moving
        await human_delay(0.1, 0.3)

        # Determine target coordinates
        box = await element.bounding_box()
        if box:
            # Pick a target point inside the element (avoiding the very edges)
            w = max(1, box['width'])
            h = max(1, box['height'])
            x_target = box['x'] + (w / 2) + random.uniform(-w/4, w/4)
            y_target = box['y'] + (h / 2) + random.uniform(-h/4, h/4)

            # Simulates trajectory.
            steps = random.randint(15, 30)
            await page.mouse.move(x_target, y_target, steps=steps)

            # Hover dwell: real humans pause 0.3-1.8s on an element before clicking
            await human_delay(0.3, 1.8)

    except Exception:
        # Fallback if bounding_box fails or element is hidden
        pass

    await element.click()

async def human_type(page, selector: str, text: str, typo_chance: float = 0.06):
    """
    Type text like a human — variable speed, occasional pauses,
    and ~6% per-word chance of making a typo then backspacing to correct it.
    """
    # Adjacent QWERTY keys for realistic typo generation
    _ADJACENT: dict = {
        'a': 'sqwz', 'b': 'vghn', 'c': 'xdfv', 'd': 'serfcx', 'e': 'wsrd',
        'f': 'drtgvc', 'g': 'ftyhbv', 'h': 'gyujnb', 'i': 'ujko', 'j': 'huikmn',
        'k': 'jiolm', 'l': 'kop', 'm': 'njk', 'n': 'bhjm', 'o': 'iklp',
        'p': 'ol', 'q': 'wa', 'r': 'edft', 's': 'qazxdew', 't': 'rfgy',
        'u': 'yhji', 'v': 'cfgb', 'w': 'qase', 'x': 'zsdc', 'y': 'tghu',
        'z': 'asx',
    }

    element = await page.wait_for_selector(selector, timeout=10000)
    await human_click(page, element)
    await human_delay(0.3, 0.8)

    for char in text:
        # Occasional typo: type a wrong adjacent key, pause briefly, then backspace
        if char.lower() in _ADJACENT and random.random() < typo_chance:
            wrong = random.choice(_ADJACENT[char.lower()])
            if char.isupper():
                wrong = wrong.upper()
            await element.type(wrong, delay=random.randint(40, 140))
            await asyncio.sleep(random.uniform(0.08, 0.35))  # moment of realisation
            await element.press('Backspace')
            await asyncio.sleep(random.uniform(0.05, 0.15))

        await element.type(char, delay=random.randint(40, 140))
        # Occasional longer pause mid-sentence (like thinking)
        if char in [' ', ',', '.'] and random.random() < 0.1:
            await asyncio.sleep(random.uniform(0.3, 0.8))


async def human_scroll(page, direction: str = "down", amount: int = None):
    """
    Scroll like a human on a trackpad:
    - Broken into 4-8 small steps with quadratic ease-out deceleration
      (big steps first, tapering off — like real trackpad momentum/friction)
    - Tiny, shrinking inter-step delay to mimic coasting to a stop
    - 15% chance of overshoot: scrolls slightly past target then bounces
      back 80-200px, exactly like a real thumb on a trackpad
    """
    if amount is None:
        amount = random.randint(300, 800)
    if direction == "up":
        amount = -amount

    # Move mouse to a realistic starting position for scrolling
    # We occasionally sweep the mouse in small gestures while scrolling down
    viewport = page.viewport_size
    if viewport:
        width = viewport.get("width", 1280)
        height = viewport.get("height", 800)
    else:
        width, height = 1280, 800

    x_scroll = random.uniform(width * 0.2, width * 0.8)
    y_scroll = random.uniform(height * 0.3, height * 0.7)
    await page.mouse.move(x_scroll, y_scroll, steps=random.randint(10, 20))
    await human_delay(0.08, 0.2)

    # --- Momentum-based multi-step scroll ---
    steps = random.randint(4, 8)

    # Quadratic ease-out weights: w_i ∝ (steps - i)  →  big steps first, small last
    raw_weights = [steps - i for i in range(steps)]
    total_w = sum(raw_weights)
    step_amounts = [int(round(amount * w / total_w)) for w in raw_weights]

    # Fix rounding so the steps sum exactly to amount
    diff = amount - sum(step_amounts)
    step_amounts[0] += diff

    # Inter-step delays also shrink (coasting friction feel)
    # First step has ~70ms delay, last has ~15ms
    base_delay = random.uniform(0.055, 0.085)
    
    current_x, current_y = x_scroll, y_scroll
    for i, step_delta in enumerate(step_amounts):
        if step_delta == 0:
            continue
            
        current_x += random.uniform(-15, 15)
        current_y += random.uniform(-10, 10)
        await page.mouse.move(current_x, current_y, steps=random.randint(1, 4))
        await page.mouse.wheel(0, step_delta)
        
        # Delay shrinks with each step: starts at base_delay, tapers to ~20%
        decay = max(0.015, base_delay * (1 - i / steps) ** 1.5)
        await asyncio.sleep(decay + random.uniform(-0.005, 0.005))

    # --- 15% overshoot: scroll past, then bounce back ---
    if random.random() < 0.15:
        overshoot = random.randint(80, 200)
        overshoot_steps = random.randint(2, 4)
        raw_w2 = [overshoot_steps - i for i in range(overshoot_steps)]
        total_w2 = sum(raw_w2)
        overshoot_deltas = [int(round(overshoot * w / total_w2)) for w in raw_w2]
        overshoot_deltas[0] += overshoot - sum(overshoot_deltas)

        await asyncio.sleep(random.uniform(0.06, 0.14))
        # Overshoot forward
        for delta in overshoot_deltas:
            await page.mouse.wheel(0, delta)
            await asyncio.sleep(random.uniform(0.02, 0.05))

        await asyncio.sleep(random.uniform(0.08, 0.18))
        # Bounce back (opposite direction)
        correction = random.randint(60, overshoot)
        correction_steps = random.randint(2, 3)
        raw_w3 = [correction_steps - i for i in range(correction_steps)]
        total_w3 = sum(raw_w3)
        correction_deltas = [int(round(-correction * w / total_w3)) for w in raw_w3]
        correction_deltas[0] += (-correction) - sum(correction_deltas)
        for delta in correction_deltas:
            await page.mouse.wheel(0, delta)
            await asyncio.sleep(random.uniform(0.02, 0.05))

    await human_delay(0.4, 1.2)

