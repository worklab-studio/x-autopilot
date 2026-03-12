"""
dashboard/server.py — Flask API backend
Serves data to the React dashboard.
Run with: python dashboard/server.py
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import json
import random
import uuid
import yaml

# Import logger functions
from agent.logger import (
    get_recent_actions,
    get_pending_tweets,
    approve_tweet,
    skip_tweet,
    get_today_stats,
    get_stats_range,
    get_growth_data,
    add_to_tweet_queue,
    DB_PATH,
    init_db
)
from agent.targets import load_targets, add_target, remove_target
from agent.hashtags import load_hashtags, add_hashtag, remove_hashtag
from agent.promotions import load_promotions, add_promotion, remove_promotion

app = Flask(__name__)
CORS(app)

# Agent state file — dashboard writes this, agent reads it
AGENT_STATE_FILE = Path(__file__).parent.parent / "data" / "agent_state.json"
MEDIA_DIR = Path(__file__).parent.parent / "data" / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

ALLOWED_MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov"}
CONFIG_ALLOWLIST = {
    "voice": {
        "niche": str,
        "product": str,
        "product_url": str,
        "personality": str,
        "never_say": list,
    },
    "posting": {
        "tweets_per_day": int,
        "tweet_times": list,
        "active_hours_start": str,
        "active_hours_end": str,
        "require_approval": bool,
        "auto_generate_tweets": bool,
        "auto_generate_threads": bool,
        "auto_generate_promos": bool,
    },
    "autonomy_mode": {
        "enabled": bool,
        "level": int,
    },
    "ui": {
        "status_overlay_enabled": bool,
    },
    "engagement": {
        "daily_replies": int,
        "daily_follows": int,
        "daily_dms": int,
        "daily_likes": int,
        "daily_retweets": int,
        "min_delay_seconds": int,
        "max_delay_seconds": int,
    },
    "dynamic_limits": {
        "enabled": bool,
        "daily_jitter_pct": float,
        "delay_jitter_pct": float,
        "hourly_jitter_pct": float,
        "session_pause_jitter_pct": float,
    },
    "tiers": {
        "small": {
            "min_followers": int,
            "max_followers": int,
            "behavior": str,
            "comment_tone": str,
            "dm_after_engagement": bool,
            "dm_delay_min_minutes": int,
            "dm_delay_max_minutes": int,
        },
        "peer": {
            "min_followers": int,
            "max_followers": int,
            "behavior": str,
            "comment_tone": str,
            "dm_after_engagement": bool,
            "dm_delay_min_minutes": int,
            "dm_delay_max_minutes": int,
        },
        "big": {
            "min_followers": int,
            "max_followers": int,
            "behavior": str,
            "comment_tone": str,
            "dm_after_engagement": bool,
            "dm_delay_min_minutes": int,
            "dm_delay_max_minutes": int,
        },
    },
    "targets": {
        "auto_add_enabled": bool,
        "auto_add_max_per_day": int,
        "auto_add_min_followers": int,
        "follow_from_mentions_enabled": bool,
        "follow_from_mentions_max_per_session": int,
        "follow_from_small_targets_only": bool,
        "follow_from_home_enabled": bool,
        "follow_from_home_max_per_session": int,
    },
    "content_topics": list,
    "content_strategy": {
        "voice_pillars": list,
        "proof_bank": list,
        "signature_angles": list,
        "weekly_direction": list,
        "tweet_templates_enabled": bool,
        "thread_templates_enabled": bool,
        "require_proof": bool,
        "require_specificity": bool,
        "enforce_no_question": bool,
        "enforce_uniqueness": bool,
        "uniqueness_window": int,
        "uniqueness_similarity_threshold": float,
        "max_generation_attempts": int,
    },
    "mentions": {
        "tools": list,
    },
    "discovery": {
        "reply_from_hashtags": bool,
        "reply_from_home_feed": bool,
        "dm_from_hashtags": bool,
        "dm_from_home_feed": bool,
        "target_profile_sessions_per_day": int,
        "max_hashtag_replies_per_session": int,
        "max_home_replies_per_session": int,
        "max_hashtag_tweets_scanned": int,
        "max_home_tweets_scanned": int,
        "hashtag_top_ratio": float,
        "profile_like_from_home_enabled": bool,
        "profile_like_profiles_per_session": int,
        "profile_like_min_posts": int,
        "profile_like_max_posts": int,
        "candidate_score_threshold": float,
        "candidate_min_words": int,
        "candidate_min_unique_ratio": float,
        "thread_topic_min_ratio": float,
        "thread_quality_min_score": float,
        "use_embeddings": bool,
        "embedding_threshold": float,
        "require_keyword_match": bool,
        "min_likes": int,
        "min_replies": int,
        "min_retweets": int,
        "min_total_engagement": int,
        "repeat_topic_window_hours": int,
        "max_topic_repeats": int,
        "relevance_keywords": list,
        "skip_bait_phrases": list,
    },
    "promotions": {
        "mentions_per_day": int,
    },
    "vision": {
        "enabled": bool,
        "model": str,
        "max_images_per_tweet": int,
        "max_image_bytes": int,
    },
    "notifications": {
        "reply_to_mentions": bool,
        "max_reply_notifications_per_session": int,
        "follow_welcome_enabled": bool,
        "max_follow_welcomes_per_session": int,
        "follow_welcome_like_min_posts": int,
        "follow_welcome_like_max_posts": int,
    },
    "safety": {
        "max_actions_per_hour": int,
        "pause_between_sessions_minutes": int,
        "rate_limit_cooldown_minutes": int,
        "dynamic_pacing": bool,
        "pacing_multiplier_max": float,
        "stop_on_rate_limit": bool,
        "never_dm_verified_accounts": bool,
        "nav_actions_per_session": int,
        "unfollow_non_followers_after_days": int,
        "idle_scroll_enabled": bool,
        "idle_scroll_interval_minutes": int,
        "idle_scroll_scrolls": int,
    },
}


def get_agent_state():
    if AGENT_STATE_FILE.exists():
        with open(AGENT_STATE_FILE) as f:
            return json.load(f)
    return {"running": True, "paused": False}


def set_agent_state(state: dict):
    AGENT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AGENT_STATE_FILE, "w") as f:
        json.dump(state, f)


def _is_allowed_media(filename: str, mimetype: str) -> bool:
    ext = Path(filename).suffix.lower()
    if ext in ALLOWED_MEDIA_EXTENSIONS:
        return True
    if mimetype and (mimetype.startswith("image/") or mimetype.startswith("video/")):
        return True
    return False


def _media_type_from_mime(mimetype: str, filename: str) -> str:
    if mimetype and mimetype.startswith("video/"):
        return "video"
    ext = Path(filename).suffix.lower()
    if ext in {".mp4", ".mov"}:
        return "video"
    return "image"


def _load_config_file() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_config_file(config: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(config, f, sort_keys=False, default_flow_style=False)


def _coerce_value(value, value_type):
    if value is None or value == "":
        return None
    if value_type is bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if value_type is int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if value_type is float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if value_type is list:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            parts = []
            for line in value.replace("\r", "\n").split("\n"):
                parts.extend([v.strip() for v in line.split(",") if v.strip()])
            return parts
        return None
    return str(value)


def _apply_config_updates(config: dict, updates: dict, allowlist: dict = None, path: list = None, applied: list = None) -> list:
    if allowlist is None:
        allowlist = CONFIG_ALLOWLIST
    if path is None:
        path = []
    if applied is None:
        applied = []
    for key, rule in allowlist.items():
        if key not in updates:
            continue
        incoming = updates.get(key)
        if isinstance(rule, dict):
            if not isinstance(incoming, dict):
                continue
            if key not in config or not isinstance(config.get(key), dict):
                config[key] = {}
            _apply_config_updates(config[key], incoming, rule, path + [key], applied)
            continue
        coerced = _coerce_value(incoming, rule)
        if coerced is None:
            continue
        config[key] = coerced
        applied.append(".".join(path + [key]))
    return applied


# ─── ROUTES ───────────────────────────────────────────

@app.route("/api/actions")
def actions():
    limit = request.args.get("limit", 50, type=int)
    return jsonify(get_recent_actions(limit=limit))


@app.route("/api/queue")
def queue():
    return jsonify(get_pending_tweets())


@app.route("/api/queue/<int:tweet_id>/approve", methods=["POST"])
def approve(tweet_id):
    # Check if edited content was sent
    data = request.get_json(silent=True) or {}
    edited_content = data.get("content")

    if edited_content:
        if not edited_content.strip():
            return jsonify({"success": False, "error": "Empty content"}), 400
        # Update the tweet content before approving
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE tweet_queue SET content = ? WHERE id = ?", (edited_content, tweet_id))
        conn.commit()
        conn.close()
    else:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT content FROM tweet_queue WHERE id = ?", (tweet_id,))
        row = c.fetchone()
        conn.close()
        if not row or not (row[0] or "").strip():
            return jsonify({"success": False, "error": "Empty content"}), 400

    approve_tweet(tweet_id)
    return jsonify({"success": True, "id": tweet_id})


@app.route("/api/queue/<int:tweet_id>/skip", methods=["POST"])
def skip(tweet_id):
    skip_tweet(tweet_id)
    return jsonify({"success": True, "id": tweet_id})


@app.route("/api/queue/<int:tweet_id>/regenerate", methods=["POST"])
def regenerate(tweet_id):
    """Regenerate a tweet — deletes old draft, creates new one."""
    try:
        from ai.tweet_writer import generate_tweet

        # Get the original tweet type from metadata if available
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT content, thread_id, thread_index, media_path, media_type FROM tweet_queue WHERE id = ?", (tweet_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return jsonify({"success": False, "error": "Tweet not found"}), 404

        # Skip the old one
        skip_tweet(tweet_id)

        # Generate a fresh one
        new_content = generate_tweet(tweet_type="auto")
        new_id = add_to_tweet_queue(
            content=new_content,
            thread_id=row[1],
            thread_index=row[2],
            media_path=row[3],
            media_type=row[4]
        )

        return jsonify({"success": True, "new_id": new_id, "content": new_content})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/queue/<int:tweet_id>/media", methods=["POST"])
def upload_queue_media(tweet_id):
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"success": False, "error": "Empty file"}), 400
    mimetype = file.mimetype or ""
    if not _is_allowed_media(file.filename, mimetype):
        return jsonify({"success": False, "error": "Unsupported media type"}), 400

    ext = Path(file.filename).suffix.lower()
    if not ext:
        ext = ".mp4" if mimetype.startswith("video/") else ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    save_path = MEDIA_DIR / filename
    file.save(save_path)

    rel_path = str(save_path.relative_to(Path(__file__).parent.parent))
    media_type = _media_type_from_mime(mimetype, file.filename)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT media_path FROM tweet_queue WHERE id = ?", (tweet_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        save_path.unlink(missing_ok=True)
        return jsonify({"success": False, "error": "Tweet not found"}), 404

    old_path = row[0]
    c.execute(
        "UPDATE tweet_queue SET media_path = ?, media_type = ? WHERE id = ?",
        (rel_path, media_type, tweet_id)
    )
    conn.commit()

    if old_path and old_path != rel_path:
        c.execute("SELECT COUNT(*) FROM tweet_queue WHERE media_path = ?", (old_path,))
        still_used = c.fetchone()
        if still_used and still_used[0] <= 1:
            old_abs = (Path(__file__).parent.parent / old_path).resolve()
            if MEDIA_DIR in old_abs.parents and old_abs.exists():
                old_abs.unlink(missing_ok=True)
    conn.close()

    return jsonify({
        "success": True,
        "media_path": rel_path,
        "media_type": media_type,
        "media_name": file.filename
    })


@app.route("/api/queue/<int:tweet_id>/media/remove", methods=["POST"])
def remove_queue_media(tweet_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT media_path FROM tweet_queue WHERE id = ?", (tweet_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "Tweet not found"}), 404

    media_path = row[0]
    c.execute("UPDATE tweet_queue SET media_path = NULL, media_type = NULL WHERE id = ?", (tweet_id,))
    conn.commit()

    if media_path:
        c.execute("SELECT COUNT(*) FROM tweet_queue WHERE media_path = ?", (media_path,))
        still_used = c.fetchone()
        if still_used and still_used[0] <= 1:
            abs_path = (Path(__file__).parent.parent / media_path).resolve()
            if MEDIA_DIR in abs_path.parents and abs_path.exists():
                abs_path.unlink(missing_ok=True)
    conn.close()

    return jsonify({"success": True})


@app.route("/api/stats")
def stats():
    range_key = request.args.get("range", "today")
    if range_key and range_key.lower() == "today":
        return jsonify(get_today_stats())
    return jsonify(get_stats_range(range_key))


@app.route("/api/growth")
def growth():
    return jsonify(get_growth_data())


@app.route("/api/agent/state")
def agent_state():
    return jsonify(get_agent_state())


@app.route("/api/agent/pause", methods=["POST"])
def pause_agent():
    state = get_agent_state()
    state["paused"] = True
    set_agent_state(state)
    return jsonify({"success": True, "paused": True})


@app.route("/api/agent/resume", methods=["POST"])
def resume_agent():
    state = get_agent_state()
    state["paused"] = False
    set_agent_state(state)
    return jsonify({"success": True, "paused": False})


@app.route("/api/agent/quit", methods=["POST"])
def quit_agent():
    """Write the quit sentinel so the agent process shuts down cleanly."""
    quit_flag = Path(__file__).parent.parent / "data" / "quit_flag"
    quit_flag.parent.mkdir(parents=True, exist_ok=True)
    quit_flag.touch()
    # Also mark as paused so the overlay shows the right state
    state = get_agent_state()
    state["paused"] = True
    set_agent_state(state)
    return jsonify({"success": True, "message": "Agent shutdown initiated"})




@app.route("/api/voice-profile")
def get_voice_profile():
    voice_path = Path(__file__).parent.parent / "ai" / "voice_profile.txt"
    if voice_path.exists():
        return jsonify({"content": voice_path.read_text()})
    return jsonify({"content": ""})


@app.route("/api/voice-profile", methods=["POST"])
def save_voice_profile():
    data = request.get_json()
    content = data.get("content", "")
    voice_path = Path(__file__).parent.parent / "ai" / "voice_profile.txt"
    voice_path.write_text(content)
    return jsonify({"success": True})


@app.route("/api/config")
def get_config():
    return jsonify(_load_config_file())


@app.route("/api/config", methods=["POST"])
def update_config():
    data = request.get_json(silent=True) or {}
    updates = data.get("config") or data.get("updates") or {}
    if not isinstance(updates, dict):
        return jsonify({"success": False, "error": "Invalid config payload"}), 400

    config = _load_config_file()
    applied = _apply_config_updates(config, updates)
    _save_config_file(config)
    return jsonify({"success": True, "applied": applied})


@app.route("/api/targets")
def targets():
    return jsonify(load_targets())


@app.route("/api/targets/add", methods=["POST"])
def targets_add():
    data = request.get_json() or {}
    username = data.get("username", "")
    tier = data.get("tier", "small")
    followers = data.get("followers")
    success = add_target(username=username, tier=tier, followers=followers)
    return jsonify({"success": success})


@app.route("/api/targets/remove", methods=["POST"])
def targets_remove():
    data = request.get_json() or {}
    username = data.get("username", "")
    success = remove_target(username=username)
    return jsonify({"success": success})


@app.route("/api/hashtags")
def hashtags():
    return jsonify({"hashtags": load_hashtags()})


@app.route("/api/hashtags/add", methods=["POST"])
def hashtags_add():
    data = request.get_json() or {}
    tag = data.get("tag", "")
    success = add_hashtag(tag)
    return jsonify({"success": success})


@app.route("/api/hashtags/remove", methods=["POST"])
def hashtags_remove():
    data = request.get_json() or {}
    tag = data.get("tag", "")
    success = remove_hashtag(tag)
    return jsonify({"success": success})


@app.route("/api/promotions")
def promotions():
    return jsonify({"promotions": load_promotions()})


@app.route("/api/promotions/add", methods=["POST"])
def promotions_add():
    data = request.get_json() or {}
    name = data.get("name", "")
    url = data.get("url", "")
    context = data.get("context", "")
    success = add_promotion(name=name, url=url, context=context)
    return jsonify({"success": success})


@app.route("/api/promotions/remove", methods=["POST"])
def promotions_remove():
    data = request.get_json() or {}
    index = data.get("index")
    try:
        index = int(index)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid index"}), 400
    success = remove_promotion(index=index)
    return jsonify({"success": success})


@app.route("/api/test-tweet", methods=["POST"])
def test_tweet():
    """Generate a test tweet without adding to queue."""
    try:
        from ai.tweet_writer import generate_tweet
        data = request.get_json() or {}
        tweet_type = data.get("type", "auto")
        content = generate_tweet(tweet_type=tweet_type)
        return jsonify({"success": True, "content": content})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/thread", methods=["POST"])
def generate_thread():
    """Generate a thread and add all parts to the queue."""
    try:
        from ai.tweet_writer import generate_thread as _generate_thread

        data = request.get_json(silent=True) or {}
        topic = data.get("topic")
        num_tweets = data.get("num_tweets", 5)
        try:
            num_tweets = int(num_tweets)
        except (TypeError, ValueError):
            num_tweets = 5
        num_tweets = max(2, min(num_tweets, 10))

        if not topic:
            config_path = Path(__file__).parent.parent / "config.yaml"
            with open(config_path) as f:
                config = yaml.safe_load(f)
            topics = config.get("content_topics", ["indie hacking"])
            topic = random.choice(topics)

        tweets = _generate_thread(topic=topic, num_tweets=num_tweets)
        thread_id = uuid.uuid4().hex
        tweet_ids = []
        for i, tweet in enumerate(tweets):
            tweet_id = add_to_tweet_queue(
                content=tweet,
                scheduled_for=f"Thread part {i + 1}/{len(tweets)}",
                thread_id=thread_id,
                thread_index=i + 1
            )
            tweet_ids.append(tweet_id)

        return jsonify({
            "success": True,
            "topic": topic,
            "count": len(tweet_ids),
            "ids": tweet_ids,
            "thread_id": thread_id
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/queue/add", methods=["POST"])
def add_to_queue():
    """Manually add a tweet to the approval queue."""
    data = request.get_json() or {}
    content = data.get("content", "")
    if not content:
        return jsonify({"success": False, "error": "No content"}), 400
    tweet_id = add_to_tweet_queue(content)
    return jsonify({"success": True, "id": tweet_id})


@app.route("/api/queue/thread/add-next", methods=["POST"])
def add_thread_next():
    """Append a new tweet to a thread (or create a new thread from a single tweet)."""
    data = request.get_json() or {}
    tweet_id = data.get("tweet_id")
    content = data.get("content", "")
    if not tweet_id:
        return jsonify({"success": False, "error": "Missing tweet_id"}), 400

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT thread_id, thread_index FROM tweet_queue WHERE id = ?", (tweet_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "Tweet not found"}), 404

    thread_id, thread_index = row
    if not thread_id:
        thread_id = uuid.uuid4().hex
        thread_index = 1
        c.execute(
            "UPDATE tweet_queue SET thread_id = ?, thread_index = ? WHERE id = ?",
            (thread_id, thread_index, tweet_id)
        )
        conn.commit()

    c.execute(
        "SELECT MAX(thread_index) FROM tweet_queue WHERE thread_id = ?",
        (thread_id,)
    )
    max_index_row = c.fetchone()
    max_index = max_index_row[0] if max_index_row and max_index_row[0] else thread_index
    next_index = max_index + 1
    conn.close()

    new_id = add_to_tweet_queue(
        content=content,
        scheduled_for=f"Thread part {next_index}",
        thread_id=thread_id,
        thread_index=next_index
    )
    return jsonify({"success": True, "id": new_id, "thread_id": thread_id, "thread_index": next_index})


@app.route("/api/trends")
def trends():
    """Return today's cached trends."""
    trends_file = Path(__file__).parent.parent / "data" / "trends_cache.json"
    if trends_file.exists():
        with open(trends_file) as f:
            return jsonify(json.load(f))
    return jsonify({"date": None, "trends": []})


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    init_db()
    port = int(os.getenv("DASHBOARD_API_PORT", "5000"))
    print(f"\n🖥  Dashboard API running at http://localhost:{port}")
    print("   Open http://localhost:3000 for the dashboard UI\n")
    app.run(port=port, debug=False)
