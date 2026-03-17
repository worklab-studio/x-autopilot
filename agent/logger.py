"""
logger.py — Action logger
Every single thing the agent does gets logged here.
The dashboard reads from this to show you the live feed.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "actions.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def init_db():
    """Create database tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Every action the agent takes
    c.execute("""
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target_user TEXT,
            target_user_followers INTEGER,
            tier TEXT,
            content TEXT,
            success INTEGER DEFAULT 1,
            error TEXT,
            metadata TEXT
        )
    """)

    # Tweet approval queue
    c.execute("""
        CREATE TABLE IF NOT EXISTS tweet_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            scheduled_for TEXT,
            content TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            approved_at TEXT,
            posted_at TEXT,
            tweet_id TEXT,
            thread_id TEXT,
            thread_index INTEGER
        )
    """)

    _ensure_column(conn, "tweet_queue", "thread_id", "TEXT")
    _ensure_column(conn, "tweet_queue", "thread_index", "INTEGER")
    _ensure_column(conn, "tweet_queue", "media_path", "TEXT")
    _ensure_column(conn, "tweet_queue", "media_type", "TEXT")

    # DM conversation tracking
    c.execute("""
        CREATE TABLE IF NOT EXISTS dm_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            followers INTEGER,
            started_at TEXT NOT NULL,
            last_message_at TEXT,
            message_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            conversation_json TEXT
        )
    """)

    # Daily follower snapshots for growth graph
    c.execute("""
        CREATE TABLE IF NOT EXISTS growth_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            followers INTEGER,
            following INTEGER,
            tweets INTEGER
        )
    """)

    # Daily action counters (for safety limits)
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_counts (
            date TEXT NOT NULL,
            action_type TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (date, action_type)
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Database initialized")


def _ensure_column(conn, table: str, column: str, col_type: str) -> None:
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in c.fetchall()]
    if column not in cols:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def log_action(
    action_type: str,
    target_user: str = None,
    target_user_followers: int = None,
    tier: str = None,
    content: str = None,
    success: bool = True,
    error: str = None,
    metadata: dict = None
):
    """Log an action to the database and print to console."""
    timestamp = datetime.now().isoformat()

    # Console output
    status_icon = "✓" if success else "✗"
    tier_tag = f"[{tier}]" if tier else ""
    user_tag = f"@{target_user}" if target_user else ""
    print(f"  {status_icon} {timestamp[11:16]} — {action_type.upper()} {user_tag} {tier_tag}")
    if content:
        preview = content[:60] + "..." if len(content) > 60 else content
        print(f"    └─ \"{preview}\"")

    # Database insert
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO actions
        (timestamp, action_type, target_user, target_user_followers, tier, content, success, error, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        timestamp,
        action_type,
        target_user,
        target_user_followers,
        tier,
        content,
        1 if success else 0,
        error,
        json.dumps(metadata) if metadata else None
    ))

    # Increment daily counter
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("""
        INSERT INTO daily_counts (date, action_type, count)
        VALUES (?, ?, 1)
        ON CONFLICT(date, action_type)
        DO UPDATE SET count = count + 1
    """, (today, action_type))

    conn.commit()
    conn.close()


def get_daily_count(action_type: str) -> int:
    """Get how many times we've done something today."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT count FROM daily_counts
        WHERE date = ? AND action_type = ?
    """, (today, action_type))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0


def is_limit_reached(action_type: str, daily_limit: int) -> bool:
    """Check if we've hit the daily limit for an action."""
    count = get_daily_count(action_type)
    if count >= daily_limit:
        print(f"⚠️  Daily limit reached for {action_type} ({count}/{daily_limit})")
        return True
    return False


def add_to_tweet_queue(
    content: str,
    scheduled_for: str = None,
    thread_id: str = None,
    thread_index: int = None,
    media_path: str = None,
    media_type: str = None
) -> int:
    """Add a generated tweet to the approval queue."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO tweet_queue (created_at, scheduled_for, content, status, thread_id, thread_index, media_path, media_type)
        VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)
    """, (datetime.now().isoformat(), scheduled_for, content, thread_id, thread_index, media_path, media_type))
    tweet_id = c.lastrowid
    conn.commit()
    conn.close()
    print(f"📝 Tweet added to approval queue (ID: {tweet_id})")
    return tweet_id


def get_pending_tweets() -> list:
    """Get all tweets waiting for approval."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, created_at, scheduled_for, content, thread_id, thread_index, media_path, media_type
        FROM tweet_queue
        WHERE status = 'pending'
        ORDER BY created_at ASC
    """)
    rows = c.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "created_at": r[1],
            "scheduled_for": r[2],
            "content": r[3],
            "thread_id": r[4],
            "thread_index": r[5],
            "media_path": r[6],
            "media_type": r[7],
        } for r in rows
    ]


def approve_tweet(tweet_id: int) -> bool:
    """Mark a tweet as approved — agent will post it."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE tweet_queue
        SET status = 'approved', approved_at = ?
        WHERE id = ?
    """, (datetime.now().isoformat(), tweet_id))
    conn.commit()
    conn.close()
    return True


def skip_tweet(tweet_id: int) -> bool:
    """Skip a tweet — won't be posted."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE tweet_queue SET status = 'skipped' WHERE id = ?
    """, (tweet_id,))
    conn.commit()
    conn.close()
    return True


def get_recent_pillars(days: int = 2) -> list:
    """Return list of pillars used in the last N days (for rotation logic)."""
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT action_type FROM daily_counts
        WHERE date >= ? AND action_type LIKE 'tweet_pillar_%' AND count > 0
    """, (cutoff,))
    rows = c.fetchall()
    conn.close()
    # Strip prefix to get raw pillar name
    return [r[0].replace("tweet_pillar_", "", 1) for r in rows]


def log_tweet_pillar(pillar: str):
    """Track which pillar was used today (for rotation)."""
    today = datetime.now().strftime("%Y-%m-%d")
    action_type = f"tweet_pillar_{pillar}"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO daily_counts (date, action_type, count)
        VALUES (?, ?, 1)
        ON CONFLICT(date, action_type)
        DO UPDATE SET count = count + 1
    """, (today, action_type))
    conn.commit()
    conn.close()


def save_growth_snapshot(followers: int, following: int, tweets: int):
    """Save today's follower count for the growth graph."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO growth_snapshots (date, followers, following, tweets)
        VALUES (?, ?, ?, ?)
    """, (today, followers, following, tweets))
    conn.commit()
    conn.close()


def get_recent_actions(limit: int = 50) -> list:
    """Get recent actions for the dashboard live feed."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT timestamp, action_type, target_user, tier, content, success
        FROM actions
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [{
        "timestamp": r[0],
        "action_type": r[1],
        "target_user": r[2],
        "tier": r[3],
        "content": r[4],
        "success": bool(r[5])
    } for r in rows]


def get_growth_data() -> list:
    """Get growth data for the graph."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT date, followers, following
        FROM growth_snapshots
        ORDER BY date ASC
        LIMIT 30
    """)
    rows = c.fetchall()
    conn.close()
    return [{"date": r[0], "followers": r[1], "following": r[2]} for r in rows]


def get_today_stats() -> dict:
    """Get today's action counts for the dashboard."""
    return get_stats_range("today")


def get_stats_range(range_key: str = "today") -> dict:
    """Get action counts for a given time range: today, month, all."""
    range_key = (range_key or "today").lower()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if range_key == "all":
        c.execute("""
            SELECT action_type, SUM(count)
            FROM daily_counts
            GROUP BY action_type
        """)
    elif range_key == "month":
        month_prefix = datetime.now().strftime("%Y-%m-")
        c.execute("""
            SELECT action_type, SUM(count)
            FROM daily_counts
            WHERE date LIKE ?
            GROUP BY action_type
        """, (f"{month_prefix}%",))
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        c.execute("""
            SELECT action_type, SUM(count)
            FROM daily_counts
            WHERE date = ?
            GROUP BY action_type
        """, (today,))

    rows = c.fetchall()
    conn.close()
    stats = {r[0]: int(r[1] or 0) for r in rows}
    return {
        "tweets": stats.get("tweet", 0),
        "replies": stats.get("reply", 0),
        "follows": stats.get("follow", 0),
        "dms": stats.get("dm", 0),
        "likes": stats.get("like", 0),
        "retweets": stats.get("retweet", 0),
    }


# Initialize DB when module loads
init_db()
