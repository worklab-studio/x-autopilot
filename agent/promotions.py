"""
promotions.py — Manage subtle product promotions.
Stored in data/promotions.json for dashboard editing.
"""

import json
from pathlib import Path

PROMOTIONS_PATH = Path(__file__).parent.parent / "data" / "promotions.json"


def load_promotions() -> list:
    if not PROMOTIONS_PATH.exists():
        return []
    with open(PROMOTIONS_PATH) as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("promotions", [])


def save_promotions(items: list) -> None:
    PROMOTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROMOTIONS_PATH, "w") as f:
        json.dump(items, f, indent=2)


def add_promotion(name: str, url: str, context: str) -> bool:
    name = (name or "").strip()
    url = (url or "").strip()
    context = (context or "").strip()
    if not name or not url or not context:
        return False
    items = load_promotions()
    items.append({"name": name, "url": url, "context": context})
    save_promotions(items)
    return True


def remove_promotion(index: int) -> bool:
    items = load_promotions()
    if index < 0 or index >= len(items):
        return False
    items.pop(index)
    save_promotions(items)
    return True
