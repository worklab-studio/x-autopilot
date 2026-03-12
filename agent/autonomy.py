"""
autonomy.py — Autonomy mode helpers (action mix + pacing profiles).
"""

import math


def _clamp(value: int, low: int = 0, high: int = 100) -> int:
    try:
        value = int(value)
    except Exception:
        return low
    return max(low, min(high, value))


def _volume_factor(level: int) -> float:
    if level <= 25:
        return 0.3 + (level / 25.0) * 0.2  # 0.30 -> 0.50
    if level <= 60:
        return 0.5 + ((level - 25.0) / 35.0) * 0.2  # 0.50 -> 0.70
    return 0.7 + ((level - 60.0) / 40.0) * 0.2  # 0.70 -> 0.90


def build_profile(level: int) -> dict:
    level = _clamp(level)
    if level <= 25:
        target_ratio = 0.7
        hashtag_ratio = 0.1
        home_reply_ratio = 0.2
        home_like_ratio = 0.2
        follow_ratio = 0.2
        profile_like_ratio = 0.1
        delay_scale = 1.3
        quality_delta = 0.08
        tier = "conservative"
    elif level <= 60:
        target_ratio = 0.45
        hashtag_ratio = 0.25
        home_reply_ratio = 0.30
        home_like_ratio = 0.30
        follow_ratio = 0.30
        profile_like_ratio = 0.25
        delay_scale = 1.0
        quality_delta = 0.0
        tier = "balanced"
    else:
        target_ratio = 0.30
        hashtag_ratio = 0.35
        home_reply_ratio = 0.35
        home_like_ratio = 0.40
        follow_ratio = 0.40
        profile_like_ratio = 0.30
        delay_scale = 0.85
        quality_delta = -0.05
        tier = "exploratory"

    exploration_ratio = 0.2 + (level / 100.0) * 0.4  # 0.2 -> 0.6

    return {
        "level": level,
        "tier": tier,
        "volume_factor": _volume_factor(level),
        "delay_scale": delay_scale,
        "quality_delta": quality_delta,
        "target_reply_ratio": target_ratio,
        "hashtag_reply_ratio": hashtag_ratio,
        "home_reply_ratio": home_reply_ratio,
        "home_like_ratio": home_like_ratio,
        "follow_ratio": follow_ratio,
        "profile_like_ratio": profile_like_ratio,
        "exploration_ratio": exploration_ratio,
        "diversity": level / 100.0,
    }


def get_autonomy_profile(config: dict) -> dict:
    mode = (config or {}).get("autonomy_mode", {}) or {}
    if not mode.get("enabled", False):
        return {"enabled": False}
    level = mode.get("level", 50)
    profile = build_profile(level)
    profile["enabled"] = True
    return profile


def scale_count(base: int, factor: float) -> int:
    if base is None:
        return 0
    if base <= 0:
        return 0
    try:
        value = int(round(base * factor))
    except Exception:
        return base
    return max(1, value)
