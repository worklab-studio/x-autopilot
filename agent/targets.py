"""
targets.py — Manage tiered target accounts.
Stores tiered targets in data/targets.json and merges config seeds.
"""

import json
import yaml
from pathlib import Path

from agent.logger import log_action, is_limit_reached

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
TARGETS_PATH = Path(__file__).parent.parent / "data" / "targets.json"


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _empty_targets() -> dict:
    return {"small": [], "peer": [], "big": []}


def _normalize(username: str) -> str:
    if not username:
        return ""
    name = username.strip()
    if name.startswith("@"):
        name = name[1:]
    return name.lower()


def _dedupe_targets(data: dict) -> dict:
    seen = set()
    cleaned = _empty_targets()
    for tier in ["small", "peer", "big"]:
        for username in data.get(tier, []):
            name = _normalize(username)
            if name and name not in seen:
                cleaned[tier].append(name)
                seen.add(name)
    return cleaned


def _seed_from_config(data: dict) -> dict:
    config = _load_config()
    for username in config.get("target_accounts", []):
        name = _normalize(username)
        if name and name not in data["small"] and name not in data["peer"] and name not in data["big"]:
            data["small"].append(name)
    return data


def load_targets() -> dict:
    if TARGETS_PATH.exists():
        with open(TARGETS_PATH) as f:
            data = json.load(f)
    else:
        data = _empty_targets()
        data = _seed_from_config(data)
        data = _dedupe_targets(data)
        save_targets(data)
        return data

    deduped = _dedupe_targets(data)
    if deduped != data:
        save_targets(deduped)
    return deduped


def save_targets(data: dict) -> None:
    TARGETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TARGETS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _classify_tier(followers: int, config: dict) -> str:
    tiers = config.get("tiers", {})
    if followers is None:
        return "small"
    if followers <= tiers.get("small", {}).get("max_followers", 1000):
        return "small"
    if followers <= tiers.get("peer", {}).get("max_followers", 10000):
        return "peer"
    return "big"


def add_target(username: str, tier: str = None, followers: int = None) -> bool:
    name = _normalize(username)
    if not name:
        return False

    config = _load_config()
    data = load_targets()
    resolved_tier = tier or _classify_tier(followers, config)

    for t in ["small", "peer", "big"]:
        if name in data.get(t, []):
            data[t] = [u for u in data[t] if u != name]

    if resolved_tier not in data:
        resolved_tier = "small"

    data[resolved_tier].append(name)
    data = _dedupe_targets(data)
    save_targets(data)
    return True


def remove_target(username: str) -> bool:
    name = _normalize(username)
    if not name:
        return False

    data = load_targets()
    changed = False
    for t in ["small", "peer", "big"]:
        if name in data.get(t, []):
            data[t] = [u for u in data[t] if u != name]
            changed = True

    if changed:
        save_targets(data)
    return changed


def get_target_accounts() -> list:
    data = load_targets()
    combined = []
    for tier in ["small", "peer", "big"]:
        combined.extend(data.get(tier, []))
    return combined


def maybe_auto_add_target(username: str, followers: int, source: str = None) -> bool:
    config = _load_config()
    settings = config.get("targets", {})
    if not settings.get("auto_add_enabled", False):
        return False

    min_followers = settings.get("auto_add_min_followers", 0)
    if followers is not None and followers < min_followers:
        return False

    max_per_day = settings.get("auto_add_max_per_day", 5)
    if is_limit_reached("target_added", max_per_day):
        return False

    added = add_target(username=username, followers=followers)
    if added:
        log_action(
            action_type="target_added",
            target_user=username,
            target_user_followers=followers,
            success=True,
            metadata={"source": source}
        )
    return added
