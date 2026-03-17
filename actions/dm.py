"""
actions/dm.py — DM engine with multi-turn conversation tracking
Only targets 0-1k accounts that engaged with your replies.
Holds real conversations — never pitches cold.
"""

import asyncio
import random
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from agent.browser import human_delay, human_click, human_navigate
from agent.logger import log_action, is_limit_reached, DB_PATH
from agent.status_overlay import set_status
from ai.tweet_writer import generate_dm_opener, generate_dm_reply
from agent.dynamic_config import load_config_with_dynamic

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config():
    return load_config_with_dynamic(CONFIG_PATH)


def get_flagged_for_dm() -> list:
    """Get accounts flagged for DM follow-up (engaged with our reply, 0-1k followers)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT username, followers, conversation_json
        FROM dm_conversations
        WHERE status = 'flagged'
        ORDER BY started_at ASC
        LIMIT 10
    """)
    rows = c.fetchall()
    conn.close()
    return [{"username": r[0], "followers": r[1], "data": json.loads(r[2] or "{}")} for r in rows]


def get_active_conversations() -> list:
    """Get conversations waiting for a reply from us."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT username, followers, message_count, conversation_json
        FROM dm_conversations
        WHERE status = 'waiting_our_reply'
        ORDER BY last_message_at ASC
        LIMIT 5
    """)
    rows = c.fetchall()
    conn.close()
    return [{
        "username": r[0],
        "followers": r[1],
        "message_count": r[2],
        "history": json.loads(r[3] or "[]")
    } for r in rows]


def update_conversation(username: str, new_message: dict, status: str):
    """Update a DM conversation in the database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get existing conversation
    c.execute("SELECT conversation_json, message_count FROM dm_conversations WHERE username = ?", (username,))
    row = c.fetchone()

    if row:
        history = json.loads(row[0] or "[]")
        if isinstance(history, dict):
            history = []  # Reset if it was the initial flagging data
        history.append(new_message)

        c.execute("""
            UPDATE dm_conversations
            SET conversation_json = ?,
                message_count = message_count + 1,
                last_message_at = ?,
                status = ?
            WHERE username = ?
        """, (json.dumps(history), datetime.now().isoformat(), status, username))

    conn.commit()
    conn.close()


def _mark_dm_reply(username: str) -> None:
    if not username:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM dm_conversations WHERE username = ?", (username,))
    row = c.fetchone()
    if row:
        c.execute("""
            UPDATE dm_conversations
            SET status = 'waiting_our_reply',
                last_message_at = ?
            WHERE username = ?
        """, (datetime.now().isoformat(), username))
    else:
        c.execute("""
            INSERT INTO dm_conversations (username, followers, started_at, last_message_at, message_count, status, conversation_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (username, None, datetime.now().isoformat(), datetime.now().isoformat(), 0, "waiting_our_reply", "[]"))
    conn.commit()
    conn.close()


async def _user_follows_you(page) -> bool:
    selectors = [
        '[data-testid="userFollowIndicator"]',
        'text="Follows you"',
        'span:has-text("Follows you")',
        'div:has-text("Follows you")',
    ]
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                return True
        except Exception:
            continue
    return False


async def send_dm(page, username: str, message: str, skip_navigation: bool = False) -> bool:
    """Send a DM to a user."""
    try:
        # Go to their profile
        if not skip_navigation:
            await human_navigate(page, f"https://x.com/{username}")

        # Click the Message button
        msg_btn_selectors = [
            '[data-testid="sendDMFromProfile"]',
            '[aria-label="Message"]',
        ]

        try:
            msg_btn = await page.wait_for_selector(", ".join(msg_btn_selectors), timeout=8000)
        except Exception:
            pass

        if not msg_btn:
            print(f"   ⚠️  @{username} has DMs disabled or button not found")
            return False

        await human_click(page, msg_btn)
        await human_delay(1.5, 3)

        # Find the DM input — Twitter DM box placeholder says "Unencrypted message"
        # The contenteditable div is the real input target
        dm_input_selectors = [
            '[data-testid="dmComposerTextInput"]',
            'div[contenteditable="true"][data-testid="dmComposerTextInput"]',
            '[aria-label="Message"]',
            'div[contenteditable="true"][aria-label="Message"]',
            # Fallback: any visible contenteditable inside the DM composer area
            'div[data-testid="DMComposer"] div[contenteditable="true"]',
        ]

        dm_input = None
        try:
            dm_input = await page.wait_for_selector(
                ", ".join(dm_input_selectors), timeout=10000
            )
        except Exception:
            pass

        if not dm_input:
            print(f"   ❌ Could not find DM input for @{username}")
            return False

        await human_click(page, dm_input)
        await human_delay(0.5, 1.0)

        # Type the message character by character like a human
        await dm_input.type(message, delay=random.randint(40, 110))
        await human_delay(0.8, 1.5)

        # The send button (arrow ↑) only appears in DOM AFTER typing.
        # Try multiple known selectors for the send button.
        send_selectors = [
            '[data-testid="dmComposerSendButton"]',
            '[aria-label="Send message"]',
            '[aria-label="Send"]',
            # The button is a role="button" inside the DM composer footer
            'div[data-testid="DMComposer"] [role="button"]:last-child',
        ]

        send_btn = None
        try:
            send_btn = await page.wait_for_selector(
                ", ".join(send_selectors), timeout=8000
            )
        except Exception:
            pass

        if send_btn:
            await human_click(page, send_btn)
            await human_delay(1.5, 2.5)
            return True

        # Fallback: hit Enter — Twitter DM also sends on Enter
        print("   ⚠️  Send button not found — attempting keyboard Enter fallback")
        await dm_input.press("Enter")
        await human_delay(1.5, 2.5)
        return True


    except Exception as e:
        print(f"❌ DM error for @{username}: {e}")
        return False


async def run_dm_session(page):
    """
    Main DM session:
    1. Send openers to newly flagged accounts
    2. Reply to ongoing conversations
    """
    config = load_config()

    if is_limit_reached("dm", config["engagement"]["daily_dms"]):
        print("⚠️  Daily DM limit reached")
        return

    # --- Step 1: Send openers to newly flagged accounts ---
    flagged = get_flagged_for_dm()
    await set_status("DM session")

    for account in flagged:
        if is_limit_reached("dm", config["engagement"]["daily_dms"]):
            break

        username = account["username"]
        data = account["data"]

        # Visit their profile before DMing to simulate human flow
        await set_status(f"DM check @{username}")
        await human_navigate(page, f"https://x.com/{username}")
        
        follows_you = await _user_follows_you(page)
        if not follows_you:
            print(f"   ℹ️  @{username} does not follow you back — attempting DM anyway")

        print(f"\n💬 Sending DM opener to @{username}...")
        await set_status(f"DM @{username}")

        # Human delay before DMing (20-90 min delay is simulated at scheduling level)
        dm_text = generate_dm_opener(
            username=username,
            their_tweet=data.get("their_tweet", ""),
            your_comment=data.get("your_reply", "")
        )

        print(f"   Message: \"{dm_text}\"")

        success = await send_dm(page, username, dm_text, skip_navigation=True)

        if success:
            log_action(
                action_type="dm",
                target_user=username,
                target_user_followers=account["followers"],
                tier="small",
                content=dm_text,
                success=True
            )

            update_conversation(
                username=username,
                new_message={"from": "agent", "text": dm_text, "timestamp": datetime.now().isoformat()},
                status="waiting_their_reply"
            )

            print(f"   ✅ DM sent to @{username}")
        else:
            # Mark as failed so we don't retry forever
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE dm_conversations SET status = 'dm_failed' WHERE username = ?", (username,))
            conn.commit()
            conn.close()

        # Human pause between DMs
        await asyncio.sleep(random.uniform(30, 90))

    # --- Step 2: Reply to ongoing conversations ---
    active_convos = get_active_conversations()

    for convo in active_convos:
        if is_limit_reached("dm", config["engagement"]["daily_dms"]):
            break

        username = convo["username"]
        history = convo["history"]
        message_count = convo["message_count"]

        # Get their latest message
        their_messages = [m for m in history if m["from"] == "them"]
        if not their_messages:
            continue

        latest = their_messages[-1]["text"]
        print(f"\n💬 Replying to @{username}'s DM: \"{latest[:50]}...\"")

        reply = generate_dm_reply(
            username=username,
            conversation_history=history,
            their_latest_message=latest,
            message_count=message_count
        )

        print(f"   Reply: \"{reply}\"")

        # For ongoing convos, we need to open the DM thread
        # (simplified — in full version this navigates to existing thread)
        success = await send_dm(page, username, reply)

        if success:
            log_action(
                action_type="dm",
                target_user=username,
                tier="small",
                content=reply,
                success=True,
                metadata={"message_number": message_count + 1}
            )

            update_conversation(
                username=username,
                new_message={"from": "agent", "text": reply, "timestamp": datetime.now().isoformat()},
                status="waiting_their_reply"
            )

        # Don't DM someone more than 4 times total
        if message_count >= 4:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE dm_conversations SET status = 'completed' WHERE username = ?", (username,))
            conn.commit()
            conn.close()
            print(f"   ✅ Conversation with @{username} marked complete")

        await asyncio.sleep(random.uniform(45, 120))

    print("\n✅ DM session complete")


async def check_dm_replies(page):
    """
    Check DM inbox for replies to our messages.
    Updates conversation status so we know who replied.
    """
    try:
        await human_navigate(page, "https://x.com/messages")

        # Get conversation list
        convos = await page.query_selector_all('[data-testid="conversation"]')

        for convo in convos[:10]:
            try:
                # Get username from conversation
                link = await convo.query_selector('a[href*="/messages/"]')
                if not link:
                    continue

                # Check for unread indicator
                unread = await convo.query_selector('[data-testid="unreadBadge"]')
                if not unread:
                    continue

                await human_click(page, convo)
                await human_delay(1.2, 2.2)

                username = ""
                try:
                    anchors = await page.query_selector_all('header a[href^="/"]')
                    if not anchors:
                        anchors = await page.query_selector_all('a[href^="/"]')
                    for anchor in anchors:
                        href = await anchor.get_attribute("href")
                        if not href:
                            continue
                        path = href.split("?")[0].strip("/")
                        if not path or "/" in path:
                            continue
                        if path in {"messages", "settings", "i", "home", "explore", "notifications"}:
                            continue
                        username = path
                        break
                except Exception:
                    username = ""

                if username:
                    _mark_dm_reply(username)
                    print(f"✅ DM reply detected from @{username}")

            except Exception:
                continue

        print("✅ DM inbox checked")

    except Exception as e:
        print(f"⚠️  Could not check DMs: {e}")
