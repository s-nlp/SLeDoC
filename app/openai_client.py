import os

import openai
from openai import AsyncOpenAI

_OPENROUTER_BASE = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
_OPENAI_BASE = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
_APP_TITLE = os.getenv("APP_TITLE", "DoSeM (Semantic Mismatch)")


def make_client(model: str):
    """Return ``(client, model_id)`` ready for `.chat.completions.create()`.

    Raises *RuntimeError* if the appropriate API key is missing.
    """

    # Heuristic: treat either "/" or ":" prefixed IDs as OpenRouter (provider/model or provider:model)
    use_openrouter = ("/" in model) or (":" in model)

    if use_openrouter:
        api_key = os.getenv("OPENROUTER_API_KEY")
        base_url = _OPENROUTER_BASE
        model_id = model  # keep provider prefix
        extra = {
            "default_headers": {
                # Recommended by OpenRouter for attribution & caching
                "HTTP-Referer": os.getenv(
                    "OPENROUTER_HTTP_REFERER", "http://localhost"
                ),
                "X-Title": _APP_TITLE,
            }
        }
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = _OPENAI_BASE
        model_id = model
        extra = {}

    if not api_key:
        kind = "OPENROUTER" if use_openrouter else "OPENAI"
        raise RuntimeError(f"Missing {kind}_API_KEY in environment.")

    return openai.OpenAI(api_key=api_key, base_url=base_url, **extra), model_id


def make_async_client(model: str):
    """Async variant of `make_client` that returns (AsyncOpenAI(), model_id)."""
    model = (model or "").strip()
    use_openrouter = ("/" in model) or (":" in model)

    if use_openrouter:
        api_key = os.getenv("OPENROUTER_API_KEY")
        base_url = _OPENROUTER_BASE
        model_id = model  # keep provider prefix
        extra = {
            "default_headers": {
                "HTTP-Referer": os.getenv(
                    "OPENROUTER_HTTP_REFERER", "http://localhost"
                ),
                "X-Title": _APP_TITLE,
            }
        }
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = _OPENAI_BASE
        model_id = model
        extra = {}

    if not api_key:
        kind = "OPENROUTER" if use_openrouter else "OPENAI"
        raise RuntimeError(f"Missing {kind}_API_KEY in environment.")

    return AsyncOpenAI(api_key=api_key, base_url=base_url, **extra), model_id
