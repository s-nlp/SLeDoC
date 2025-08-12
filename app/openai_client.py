from __future__ import annotations

import os

import openai

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_OPENAI_BASE = "https://api.openai.com/v1"


def make_client(model: str):
    """Return ``(client, model_id)`` ready for `.chat.completions.create()`.

    Raises *RuntimeError* if the appropriate API key is missing.
    """

    use_openrouter = "/" in model  # heuristic – OpenRouter models have provider prefix

    if use_openrouter:
        api_key = os.getenv("OPENROUTER_API_KEY")
        base_url = _OPENROUTER_BASE
        model_id = model  # *do not* strip provider prefix!
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = _OPENAI_BASE
        model_id = model

    if not api_key:
        kind = "OPENROUTER" if use_openrouter else "OPENAI"
        raise RuntimeError(f"Missing {kind}_API_KEY in environment.")

    return openai.OpenAI(api_key=api_key, base_url=base_url), model_id
