"""
LLM utility functions — shared across the application.

Provides:
- resolve_api_key: Unified API key resolution (model-specific → env var)
- call_llm_chat: Unified OpenAI-compatible chat completion call
- PROVIDER_ENV_MAP: Provider → environment variable mapping
"""
import os
import json
import urllib.request
from typing import Optional
from openai import OpenAI

# ── Provider → environment variable mapping ────────────────────────────────
# Extend this dict when adding new providers.
PROVIDER_ENV_MAP: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "zhipu": "ZHIPU_API_KEY",
    "glm": "ZHIPU_API_KEY",
    "chatglm": "ZHIPU_API_KEY",
    "aliyun": "ALIBABA_API_KEY",
    "qwen": "QWEN_API_KEY",
    "ollama": "",  # Ollama doesn't need an API key
}


def resolve_api_key(model: dict, provider: str = None) -> str:
    """Resolve API key for a model.

    Resolution order:
      1. model['api_key'] (model-specific key from DB)
      2. Environment variable mapped from provider name
      3. Empty string (Ollama fallback)

    Args:
        model: dict with at least 'api_key' key, or an object with .api_key attribute
        provider: provider name (e.g. 'openai', 'deepseek'). If None, inferred from model.

    Returns:
        API key string, or empty string if not found.
    """
    # Try model-specific key first
    if isinstance(model, dict):
        api_key = model.get("api_key") or ""
        provider = provider or model.get("provider", "")
    else:
        api_key = getattr(model, "api_key", None) or ""
        provider = provider or getattr(model, "provider", "")

    if api_key:
        return api_key

    # Fallback to environment variable
    provider_lower = provider.lower().strip()
    env_key = PROVIDER_ENV_MAP.get(provider_lower, "")
    if env_key:
        return os.getenv(env_key, "")

    # Try generic pattern: {PROVIDER}_API_KEY
    generic_key = f"{provider_lower.upper()}_API_KEY"
    val = os.getenv(generic_key)
    if val:
        return val

    # Ollama fallback
    if provider_lower == "ollama":
        return "ollama"

    return ""


def call_llm_chat(
    api_key: str,
    model_id: str,
    messages: list,
    api_base: str = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    timeout: int = 30,
) -> Optional[str]:
    """Call an OpenAI-compatible chat completion API and return the response text.

    Uses the `openai` SDK if available, falls back to `urllib.request`.

    Args:
        api_key: API key for authentication.
        model_id: Model identifier (e.g. 'gpt-4o', 'deepseek-chat').
        messages: List of message dicts with 'role' and 'content'.
        api_base: Base URL for the API (default: https://api.openai.com/v1).
        max_tokens: Maximum tokens in the response.
        temperature: Sampling temperature.
        timeout: Request timeout in seconds.

    Returns:
        Response text string, or None on failure.
    """
    if not api_key:
        return None

    base_url = (api_base or "https://api.openai.com/v1").rstrip("/")

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model_id,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()
    except ImportError:
        pass
    except Exception:
        # Fall through to urllib fallback
        pass

    # Fallback: use urllib.request
    try:
        payload = json.dumps({
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        result = json.loads(resp.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"].strip()
    except Exception:
        return None
