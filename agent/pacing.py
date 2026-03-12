"""
pacing.py — Dynamic throttling and cooldowns for safety.
"""

import json
import time
from pathlib import Path

from agent.logger import get_daily_count

STATE_PATH = Path(__file__).parent.parent / "data" / "pacing_state.json"


def _load_state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def cooldown_remaining_seconds() -> int:
    state = _load_state()
    until = state.get("cooldown_until")
    if not until:
        return 0
    remaining = int(until - time.time())
    return max(0, remaining)


def record_rate_limit(action_type: str, cooldown_minutes: int, reason: str = None) -> None:
    state = _load_state()
    state["cooldown_until"] = time.time() + (cooldown_minutes * 60)
    state["last_rate_limit_action"] = action_type
    state["last_reason"] = reason
    _save_state(state)


def get_delay_multiplier(config: dict, action_type: str) -> float:
    safety = config.get("safety", {})
    if not safety.get("dynamic_pacing", True):
        return 1.0

    limits = {
        "reply": config.get("engagement", {}).get("daily_replies", 0),
        "like": config.get("engagement", {}).get("daily_likes", 0),
        "follow": config.get("engagement", {}).get("daily_follows", 0),
        "dm": config.get("engagement", {}).get("daily_dms", 0),
    }

    limit = limits.get(action_type, 0) or 0
    count = get_daily_count(action_type) if limit else 0
    ratio = (count / limit) if limit else 0.0

    multiplier = 1.0
    if ratio >= 0.9:
        multiplier = 2.5
    elif ratio >= 0.7:
        multiplier = 1.6

    if cooldown_remaining_seconds() > 0:
        multiplier = max(multiplier, 2.5)

    max_mult = safety.get("pacing_multiplier_max", 3.0)
    return min(multiplier, max_mult)


async def sleep_with_pacing(base_seconds: float, config: dict, action_type: str) -> None:
    import asyncio
    import random
    mult = get_delay_multiplier(config, action_type)
    jitter = random.uniform(0.9, 1.1)
    await asyncio.sleep(base_seconds * mult * jitter)
