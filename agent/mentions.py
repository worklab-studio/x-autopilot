"""
mentions.py — handle tool mentions and typeahead selection for @handles.
"""

import asyncio
import random
import re


MENTION_RE = re.compile(r"@([A-Za-z0-9_]{1,15})")


def _normalize_handle(handle: str) -> str:
    handle = (handle or "").strip()
    if handle.startswith("@"):
        handle = handle[1:]
    return handle


def _parse_tool_entries(raw_list):
    items = []
    for raw in raw_list or []:
        entry = (raw or "").strip()
        if not entry:
            continue
        name = ""
        handle = ""
        aliases = []
        if "|" in entry:
            parts = [p.strip() for p in entry.split("|")]
            if parts:
                name = parts[0]
            if len(parts) > 1:
                handle = parts[1]
            if len(parts) > 2:
                aliases = [a.strip() for a in parts[2].split(",") if a.strip()]
        elif ":" in entry:
            left, right = entry.split(":", 1)
            name = left.strip()
            handle = right.strip()
        elif "@" in entry:
            handle = entry.strip()
        else:
            name = entry.strip()
            handle = entry.strip()

        handle = _normalize_handle(handle)
        if not handle:
            continue
        if not name:
            name = handle
        merged_aliases = [name]
        merged_aliases.extend(aliases)
        items.append({
            "name": name,
            "handle": handle,
            "aliases": merged_aliases,
        })
    return items


def apply_tool_mentions(text: str, config: dict) -> str:
    if not text:
        return text
    mention_cfg = (config or {}).get("mentions", {})
    items = _parse_tool_entries(mention_cfg.get("tools") or [])
    if not items:
        return text

    alias_map = []
    for item in items:
        handle = item.get("handle")
        if not handle:
            continue
        for alias in item.get("aliases") or []:
            alias = (alias or "").strip()
            if not alias or alias.startswith("@"):
                continue
            alias_map.append((alias, handle))

    alias_map.sort(key=lambda pair: len(pair[0]), reverse=True)
    updated = text
    for alias, handle in alias_map:
        pattern = re.compile(rf"(?<![@#\w/]){re.escape(alias)}(?![\w/])", re.IGNORECASE)
        updated = pattern.sub(f"@{handle}", updated)

    return updated


async def _has_typeahead_results(page) -> bool:
    selectors = [
        '[data-testid="typeaheadResult"]',
        '[role="listbox"] [role="option"]',
    ]
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                return True
        except Exception:
            continue
    return False


async def type_with_mentions(page, element, text: str, delay_range=(40, 120)):
    if not text:
        return
    delay = random.randint(*delay_range)
    cursor = 0
    for match in MENTION_RE.finditer(text):
        prefix = text[cursor:match.start()]
        if prefix:
            await element.type(prefix, delay=delay)
        handle = match.group(1)
        await element.type(f"@{handle}", delay=delay)
        await asyncio.sleep(random.uniform(0.2, 0.5))
        if await _has_typeahead_results(page):
            await page.keyboard.press("Enter")
            await asyncio.sleep(random.uniform(0.1, 0.3))
        cursor = match.end()

    remainder = text[cursor:]
    if remainder:
        await element.type(remainder, delay=delay)
