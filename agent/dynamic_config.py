"""
dynamic_config.py — Load config with stable daily jitter for limits and pacing.
"""

import hashlib
import json
import random
from datetime import datetime
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
from agent.autonomy import get_autonomy_profile, scale_count


def _stable_seed(signature: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return f"{today}:{signature}"


def _signature(data: dict) -> str:
    payload = json.dumps(data, sort_keys=True, default=str)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def _jitter_int(value, pct, rng, minimum=0):
    if value is None:
        return None
    delta = value * pct
    new_value = value + rng.uniform(-delta, delta)
    return max(minimum, int(round(new_value)))


def _jitter_float(value, pct, rng, minimum=0.0):
    if value is None:
        return None
    delta = value * pct
    new_value = value + rng.uniform(-delta, delta)
    return max(minimum, float(new_value))


def load_config_with_dynamic(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        config = yaml.safe_load(f) or {}

    dyn = config.get("dynamic_limits", {}) or {}
    if not dyn.get("enabled", False):
        profile = get_autonomy_profile(config)
        if profile.get("enabled"):
            _apply_autonomy(config, profile)
        return config

    daily_pct = float(dyn.get("daily_jitter_pct", 0.2) or 0.2)
    delay_pct = float(dyn.get("delay_jitter_pct", 0.25) or 0.25)
    hourly_pct = float(dyn.get("hourly_jitter_pct", 0.2) or 0.2)
    pause_pct = float(dyn.get("session_pause_jitter_pct", 0.25) or 0.25)

    base_snapshot = {
        "engagement": config.get("engagement", {}),
        "safety": {
            "max_actions_per_hour": (config.get("safety", {}) or {}).get("max_actions_per_hour"),
            "pause_between_sessions_minutes": (config.get("safety", {}) or {}).get("pause_between_sessions_minutes"),
        },
        "dynamic_limits": {
            "daily_jitter_pct": daily_pct,
            "delay_jitter_pct": delay_pct,
            "hourly_jitter_pct": hourly_pct,
            "session_pause_jitter_pct": pause_pct,
        },
    }

    rng = random.Random(_stable_seed(_signature(base_snapshot)))

    engagement = config.setdefault("engagement", {})
    for key in ("daily_replies", "daily_follows", "daily_dms", "daily_likes", "daily_retweets"):
        if key in engagement:
            engagement[key] = _jitter_int(engagement.get(key), daily_pct, rng, minimum=0)

    min_delay = engagement.get("min_delay_seconds")
    max_delay = engagement.get("max_delay_seconds")
    if min_delay is not None:
        engagement["min_delay_seconds"] = _jitter_int(min_delay, delay_pct, rng, minimum=5)
    if max_delay is not None:
        engagement["max_delay_seconds"] = _jitter_int(max_delay, delay_pct, rng, minimum=10)
    if engagement.get("min_delay_seconds") is not None and engagement.get("max_delay_seconds") is not None:
        if engagement["min_delay_seconds"] >= engagement["max_delay_seconds"]:
            engagement["max_delay_seconds"] = engagement["min_delay_seconds"] + 5

    safety = config.setdefault("safety", {})
    if safety.get("max_actions_per_hour") is not None:
        safety["max_actions_per_hour"] = _jitter_int(safety.get("max_actions_per_hour"), hourly_pct, rng, minimum=1)
    if safety.get("pause_between_sessions_minutes") is not None:
        safety["pause_between_sessions_minutes"] = _jitter_int(
            safety.get("pause_between_sessions_minutes"),
            pause_pct,
            rng,
            minimum=10,
        )

    profile = get_autonomy_profile(config)
    if profile.get("enabled"):
        _apply_autonomy(config, profile)
    return config


def _apply_autonomy(config: dict, profile: dict) -> None:
    config.setdefault("autonomy_mode", {})
    config["autonomy_mode"]["profile"] = profile

    engagement = config.setdefault("engagement", {})
    volume_factor = float(profile.get("volume_factor", 1.0))
    for key in ("daily_replies", "daily_follows", "daily_dms", "daily_likes", "daily_retweets"):
        value = engagement.get(key)
        if value is None:
            continue
        engagement[key] = scale_count(int(value), volume_factor)

    delay_scale = float(profile.get("delay_scale", 1.0))
    if engagement.get("min_delay_seconds") is not None:
        engagement["min_delay_seconds"] = max(5, int(round(engagement["min_delay_seconds"] * delay_scale)))
    if engagement.get("max_delay_seconds") is not None:
        engagement["max_delay_seconds"] = max(10, int(round(engagement["max_delay_seconds"] * delay_scale)))
    if engagement.get("min_delay_seconds") is not None and engagement.get("max_delay_seconds") is not None:
        if engagement["min_delay_seconds"] >= engagement["max_delay_seconds"]:
            engagement["max_delay_seconds"] = engagement["min_delay_seconds"] + 5

    discovery = config.setdefault("discovery", {})
    quality_delta = float(profile.get("quality_delta", 0.0))
    if discovery.get("candidate_score_threshold") is not None:
        updated = float(discovery.get("candidate_score_threshold")) + quality_delta
        discovery["candidate_score_threshold"] = max(0.1, min(0.9, updated))
    if discovery.get("thread_quality_min_score") is not None:
        updated = float(discovery.get("thread_quality_min_score")) + quality_delta
        discovery["thread_quality_min_score"] = max(0.1, min(0.9, updated))

    if discovery.get("profile_like_profiles_per_session") is not None:
        base = int(discovery.get("profile_like_profiles_per_session") or 0)
        factor = float(profile.get("profile_like_ratio", 0.25)) / 0.25
        discovery["profile_like_profiles_per_session"] = max(0, int(round(base * factor)))
