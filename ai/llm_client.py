"""
llm_client.py — Unified text + vision calls for Anthropic and OpenAI.
"""

import os
from typing import Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()


class LLMConfigError(RuntimeError):
    """Raised when LLM provider configuration is invalid."""


DEFAULT_TEXT_MODELS = {
    "anthropic": "claude-opus-4-6",
    "openai": "gpt-4o-mini",
}

DEFAULT_VISION_MODELS = {
    "anthropic": "claude-3-5-sonnet-20241022",
    "openai": "gpt-4o-mini",
}

FALLBACK_TEXT_MODELS = {
    "anthropic": ["claude-opus-4-6", "claude-3-7-sonnet-latest", "claude-3-5-sonnet-20241022"],
    "openai": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"],
}

FALLBACK_VISION_MODELS = {
    "anthropic": ["claude-3-5-sonnet-20241022", "claude-opus-4-6"],
    "openai": ["gpt-4o-mini", "gpt-4o"],
}

_ANTHROPIC_CLIENT = None
_OPENAI_CLIENT = None


def _clean(value: Optional[str]) -> str:
    return (value or "").strip()


def _normalize_provider(value: str) -> str:
    provider = _clean(value).lower() or "auto"
    if provider not in {"auto", "anthropic", "openai"}:
        raise LLMConfigError("Invalid LLM_PROVIDER. Use: auto, anthropic, or openai.")
    return provider


def resolve_provider(preferred: Optional[str] = None) -> str:
    requested = _normalize_provider(preferred or os.getenv("LLM_PROVIDER", "auto"))
    has_anthropic = bool(_clean(os.getenv("ANTHROPIC_API_KEY")))
    has_openai = bool(_clean(os.getenv("OPENAI_API_KEY")))

    if requested == "auto":
        if has_anthropic:
            return "anthropic"
        if has_openai:
            return "openai"
        raise LLMConfigError("No API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY.")

    if requested == "anthropic" and not has_anthropic:
        raise LLMConfigError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is missing.")
    if requested == "openai" and not has_openai:
        raise LLMConfigError("LLM_PROVIDER=openai but OPENAI_API_KEY is missing.")
    return requested


def _model_looks_wrong_for_provider(model: str, provider: str) -> bool:
    lowered = (model or "").lower()
    if provider == "openai":
        return "claude" in lowered
    if provider == "anthropic":
        return any(token in lowered for token in ("gpt", "o1", "o3", "o4"))
    return False


def resolve_model(kind: str = "text", requested_model: Optional[str] = None, provider: Optional[str] = None) -> str:
    actual_provider = resolve_provider(provider)
    requested = _clean(requested_model)
    if requested and not _model_looks_wrong_for_provider(requested, actual_provider):
        return requested

    if kind == "vision":
        env_key = "ANTHROPIC_VISION_MODEL" if actual_provider == "anthropic" else "OPENAI_VISION_MODEL"
        return _clean(os.getenv(env_key)) or DEFAULT_VISION_MODELS[actual_provider]

    env_key = "ANTHROPIC_TEXT_MODEL" if actual_provider == "anthropic" else "OPENAI_TEXT_MODEL"
    return _clean(os.getenv(env_key)) or DEFAULT_TEXT_MODELS[actual_provider]


def _anthropic_client():
    global _ANTHROPIC_CLIENT
    if _ANTHROPIC_CLIENT is not None:
        return _ANTHROPIC_CLIENT

    api_key = _clean(os.getenv("ANTHROPIC_API_KEY"))
    if not api_key:
        raise LLMConfigError("ANTHROPIC_API_KEY is missing.")

    try:
        import anthropic
    except ImportError as exc:
        raise LLMConfigError("anthropic package not installed. Run: pip install anthropic") from exc

    _ANTHROPIC_CLIENT = anthropic.Anthropic(api_key=api_key)
    return _ANTHROPIC_CLIENT


def _openai_client():
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is not None:
        return _OPENAI_CLIENT

    api_key = _clean(os.getenv("OPENAI_API_KEY"))
    if not api_key:
        raise LLMConfigError("OPENAI_API_KEY is missing.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMConfigError("openai package not installed. Run: pip install openai") from exc

    _OPENAI_CLIENT = OpenAI(api_key=api_key)
    return _OPENAI_CLIENT


def _extract_anthropic_text(response) -> str:
    chunks = []
    for item in getattr(response, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip()


def _extract_openai_text(response) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    if not message:
        return ""

    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        chunks = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and item.get("text"):
                chunks.append(item["text"])
        return "\n".join(chunks).strip()

    return ""


def _candidate_models(kind: str, provider: str, primary: str) -> List[str]:
    if kind == "vision":
        fallback = FALLBACK_VISION_MODELS.get(provider, [])
    else:
        fallback = FALLBACK_TEXT_MODELS.get(provider, [])

    seen = set()
    ordered = []
    for model in [primary] + fallback:
        if model and model not in seen:
            ordered.append(model)
            seen.add(model)
    return ordered


def _is_model_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "model" in text and "not found" in text
    ) or (
        "not_found_error" in text
    ) or (
        "does not exist" in text
    ) or (
        "invalid model" in text
    )


def chat_text(
    prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 300,
    system: Optional[str] = None,
    temperature: Optional[float] = None,
    provider: Optional[str] = None,
) -> str:
    actual_provider = resolve_provider(provider)
    primary_model = resolve_model(kind="text", requested_model=model, provider=actual_provider)
    model_candidates = _candidate_models("text", actual_provider, primary_model)

    if actual_provider == "anthropic":
        client = _anthropic_client()
        last_exc = None
        for model_name in model_candidates:
            payload = {
                "model": model_name,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                payload["system"] = system
            if temperature is not None:
                payload["temperature"] = temperature
            try:
                response = client.messages.create(**payload)
                return _extract_anthropic_text(response)
            except Exception as exc:
                last_exc = exc
                if _is_model_error(exc):
                    continue
                raise
        if last_exc:
            raise last_exc

    client = _openai_client()
    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    last_exc = None
    for model_name in model_candidates:
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        try:
            response = client.chat.completions.create(**payload)
            return _extract_openai_text(response)
        except Exception as exc:
            last_exc = exc
            if _is_model_error(exc):
                continue
            raise
    if last_exc:
        raise last_exc
    return ""


def chat_vision(
    prompt: str,
    images: List[Dict[str, str]],
    model: Optional[str] = None,
    max_tokens: int = 200,
    temperature: Optional[float] = None,
    provider: Optional[str] = None,
) -> str:
    if not images:
        return ""

    actual_provider = resolve_provider(provider)
    primary_model = resolve_model(kind="vision", requested_model=model, provider=actual_provider)
    model_candidates = _candidate_models("vision", actual_provider, primary_model)

    if actual_provider == "anthropic":
        client = _anthropic_client()
        last_exc = None
        for model_name in model_candidates:
            content = [{"type": "text", "text": prompt}]
            for image in images:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image["media_type"],
                        "data": image["data"],
                    },
                })

            payload = {
                "model": model_name,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": content}],
            }
            if temperature is not None:
                payload["temperature"] = temperature
            try:
                response = client.messages.create(**payload)
                return _extract_anthropic_text(response)
            except Exception as exc:
                last_exc = exc
                if _is_model_error(exc):
                    continue
                raise
        if last_exc:
            raise last_exc

    client = _openai_client()
    last_exc = None
    for model_name in model_candidates:
        content = [{"type": "text", "text": prompt}]
        for image in images:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{image['media_type']};base64,{image['data']}"},
            })

        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        try:
            response = client.chat.completions.create(**payload)
            return _extract_openai_text(response)
        except Exception as exc:
            last_exc = exc
            if _is_model_error(exc):
                continue
            raise
    if last_exc:
        raise last_exc
    return ""
