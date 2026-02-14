import json
import os
import types
from typing import Dict, Optional

import httpx
import openai
from openai import AsyncOpenAI

_OPENROUTER_BASE = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
_OPENAI_BASE = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
_APP_TITLE = os.getenv("APP_TITLE", "SLeDoC")

# Local FastAPI settings
_LOCAL_BASE = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:8000")
_LOCAL_ROUTE = os.getenv("LOCAL_LLM_CHAT_ROUTE", "/v1/chat/completions")
_LOCAL_TIMEOUT = float(os.getenv("LOCAL_LLM_TIMEOUT_S", "60"))
_LOCAL_HEADERS_JSON = os.getenv("LOCAL_LLM_HEADERS_JSON", "")


def _local_headers() -> Dict[str, str]:
    """local headers for local LLM calls from JSON env var."""
    if not _LOCAL_HEADERS_JSON:
        return {}
    try:
        parsed = json.loads(_LOCAL_HEADERS_JSON)
        return {str(k): str(v) for k, v in parsed.items()}
    except Exception:
        return {}


def _is_openrouter_model(model: str) -> bool:
    return ("/" in model) or (":" in model and not model.startswith("local:"))


def _want_local_provider(model: str) -> bool:
    env = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if env in {"local", "local-openai", "local-generic"}:
        return True
    return model.strip().lower().startswith("local:")


def _want_openrouter_provider() -> bool:
    env = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    return env in {"openrouter", "openrouter.ai", "openrouter-ai", "router"}


def _normalize_local_model(model: str) -> str:
    return model.split(":", 1)[1] if model.lower().startswith("local:") else model


# Local OpenAI-like client for local LLMs with OpenAI-compatible API
class _RespMessage:
    def __init__(self, content: str):
        self.content = content


class _RespChoice:
    def __init__(self, message: _RespMessage):
        self.message = message


class _RespObj:
    """Mimics OpenAI's response: .choices[0].message.content"""

    def __init__(self, content: str):
        self.choices = [_RespChoice(_RespMessage(content))]


class _LocalSyncChatCompletions:
    def __init__(self, http: httpx.Client, route: str):
        self._http = http
        self._route = route

    def create(self, *, model: str, temperature: float, messages: list[dict[str, str]]):
        payload = {"model": model, "messages": messages, "temperature": temperature}
        r = self._http.post(self._route, json=payload)
        r.raise_for_status()
        data = r.json()

        # Try OpenAI-like first
        content: Optional[str] = None
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception:
            # Try more generic shapes
            if isinstance(data, str):
                content = data
            elif isinstance(data, dict):
                for key in ("text", "output", "reply", "content"):
                    if key in data and isinstance(data[key], str):
                        content = data[key]
                        break
                if content is None and "choices" in data and data["choices"]:
                    c0 = data["choices"][0]
                    if (
                        isinstance(c0, dict)
                        and "text" in c0
                        and isinstance(c0["text"], str)
                    ):
                        content = c0["text"]

        if content is None:
            raise openai.OpenAIError(f"Local LLM: cannot parse response: {data!r}")
        return _RespObj(content)


class _LocalSyncClient:
    def __init__(
        self, base_url: str, route: str, headers: Dict[str, str], timeout: float
    ):
        self._http = httpx.Client(base_url=base_url, headers=headers, timeout=timeout)
        self.chat = types.SimpleNamespace(
            completions=_LocalSyncChatCompletions(self._http, route)
        )

    def close(self):
        self._http.close()


class _LocalAsyncChatCompletions:
    def __init__(self, http: httpx.AsyncClient, route: str):
        self._http = http
        self._route = route

    async def create(
        self, *, model: str, temperature: float, messages: list[dict[str, str]]
    ):
        payload = {"model": model, "messages": messages, "temperature": temperature}
        r = await self._http.post(self._route, json=payload)
        r.raise_for_status()
        data = r.json()

        # Try OpenAI-like first
        content: Optional[str] = None
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception:
            if isinstance(data, str):
                content = data
            elif isinstance(data, dict):
                for key in ("text", "output", "reply", "content"):
                    if key in data and isinstance(data[key], str):
                        content = data[key]
                        break
                if content is None and "choices" in data and data["choices"]:
                    c0 = data["choices"][0]
                    if (
                        isinstance(c0, dict)
                        and "text" in c0
                        and isinstance(c0["text"], str)
                    ):
                        content = c0["text"]

        if content is None:
            raise openai.OpenAIError(f"Local LLM: cannot parse response: {data!r}")
        return _RespObj(content)


class _LocalAsyncClient:
    def __init__(
        self, base_url: str, route: str, headers: Dict[str, str], timeout: float
    ):
        self._http = httpx.AsyncClient(
            base_url=base_url, headers=headers, timeout=timeout
        )
        self.chat = types.SimpleNamespace(
            completions=_LocalAsyncChatCompletions(self._http, route)
        )

    async def aclose(self):
        await self._http.aclose()


def make_client(model: str):
    """
    Return (client, model_id) ready for `.chat.completions.create(...)`.
    Works with OpenAI, OpenRouter, or a local FastAPI backend if LLM_PROVIDER=local
    (or if model starts with "local:").
    """
    model = (model or "").strip()

    if _want_local_provider(model):
        # Local FastAPI backend
        headers = _local_headers()
        model_id = _normalize_local_model(model) or "local"
        client = _LocalSyncClient(_LOCAL_BASE, _LOCAL_ROUTE, headers, _LOCAL_TIMEOUT)
        return client, model_id

    # OpenRouter or OpenAI
    use_openrouter = _want_openrouter_provider() or _is_openrouter_model(model)
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

    return openai.OpenAI(api_key=api_key, base_url=base_url, **extra), model_id


def make_async_client(model: str):
    """
    Async variant: returns (AsyncOpenAI-like client, model_id).
    """
    model = (model or "").strip()

    if _want_local_provider(model):
        headers = _local_headers()
        model_id = _normalize_local_model(model) or "local"
        client = _LocalAsyncClient(_LOCAL_BASE, _LOCAL_ROUTE, headers, _LOCAL_TIMEOUT)
        return client, model_id

    use_openrouter = _want_openrouter_provider() or _is_openrouter_model(model)
    if use_openrouter:
        api_key = os.getenv("OPENROUTER_API_KEY")
        base_url = _OPENROUTER_BASE
        model_id = model
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
