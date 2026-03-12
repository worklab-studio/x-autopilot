"""
vision.py — Image understanding helper for Anthropic/OpenAI.
Returns short image descriptions to improve reply relevance.
"""

import base64
import mimetypes
import urllib.request

from dotenv import load_dotenv
from ai.llm_client import chat_vision

load_dotenv()


def _fetch_image_bytes(url: str, max_bytes: int) -> tuple:
    if url.startswith("data:"):
        header, data = url.split(",", 1)
        media_type = header.split(";")[0].replace("data:", "") or "image/jpeg"
        raw = base64.b64decode(data)
        if len(raw) > max_bytes:
            raw = raw[:max_bytes]
        return raw, media_type

    with urllib.request.urlopen(url, timeout=10) as resp:
        raw = resp.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raw = raw[:max_bytes]
        media_type = resp.headers.get_content_type()
        if not media_type:
            media_type = mimetypes.guess_type(url)[0] or "image/jpeg"
        return raw, media_type


def describe_images(image_urls: list, model: str = None, max_images: int = 2, max_bytes: int = 2000000) -> str:
    if not image_urls:
        return ""

    selected = image_urls[:max_images]
    images = []

    for url in selected:
        try:
            raw, media_type = _fetch_image_bytes(url, max_bytes=max_bytes)
        except Exception:
            continue

        images.append({
            "media_type": media_type,
            "data": base64.b64encode(raw).decode("utf-8"),
        })

    if not images:
        return ""

    try:
        return chat_vision(
            prompt="Describe each image briefly for context. One sentence per image.",
            images=images,
            model=model,
            max_tokens=200,
        )
    except Exception:
        return ""
