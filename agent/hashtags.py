"""
hashtags.py — Manage discovery hashtags.
Stores hashtags in data/hashtags.json and merges config seeds.
"""

import json
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
HASHTAGS_PATH = Path(__file__).parent.parent / "data" / "hashtags.json"


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _normalize(tag: str) -> str:
    if not tag:
        return ""
    clean = tag.strip()
    if clean.startswith("#"):
        clean = clean[1:]
    return clean.lower()


def load_hashtags() -> list:
    if HASHTAGS_PATH.exists():
        with open(HASHTAGS_PATH) as f:
            data = json.load(f)
        tags = data if isinstance(data, list) else data.get("hashtags", [])
    else:
        config = _load_config()
        tags = config.get("discovery", {}).get("hashtags", [])
        tags = [_normalize(t) for t in tags if _normalize(t)]
        save_hashtags(tags)
        return tags

    cleaned = []
    seen = set()
    for tag in tags:
        t = _normalize(tag)
        if t and t not in seen:
            cleaned.append(t)
            seen.add(t)
    return cleaned


def save_hashtags(tags: list) -> None:
    HASHTAGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HASHTAGS_PATH, "w") as f:
        json.dump(tags, f, indent=2)


def add_hashtag(tag: str) -> bool:
    t = _normalize(tag)
    if not t:
        return False
    tags = load_hashtags()
    if t in tags:
        return False
    tags.append(t)
    save_hashtags(tags)
    return True


def remove_hashtag(tag: str) -> bool:
    t = _normalize(tag)
    tags = load_hashtags()
    if t not in tags:
        return False
    tags = [x for x in tags if x != t]
    save_hashtags(tags)
    return True
