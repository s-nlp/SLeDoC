import asyncio
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

import openai
from tenacity import (
    AsyncRetrying,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from app.config import CLAIM_EXTRACTOR_SYSTEM_PROMPT as DEFAULT_SYSTEM_PROMPT
from app.config import DEFAULT_MODEL, LLM_MAX_PARALLEL
from app.openai_client import make_async_client, make_client

os.environ["TOKENIZERS_PARALLELISM"] = "True"


def run_claim_extraction(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    system_prompt: str = "",
    model_name: str = DEFAULT_MODEL,
    temperature: float = 0.2,
) -> Path:
    """Sync wrapper around `run_claim_extraction_async` enabling parallel LLM calls."""
    # Fallback order: UI -> ENV -> DEFAULT
    resolved_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    return asyncio.run(
        run_claim_extraction_async(
            input_path,
            output_path=output_path,
            system_prompt=resolved_prompt,
            model_name=model_name,
            temperature=temperature,
            max_concurrency=LLM_MAX_PARALLEL,
        )
    )


# Low-level OpenAI wrapper with basic exponential-back-off
@retry(
    wait=wait_random_exponential(multiplier=1, max=20),
    stop=stop_after_attempt(6),
    retry=retry_if_exception_type(openai.OpenAIError),
)
def _chat_completion(
    prompt: str,
    system_prompt: str,
    model_name: str,
    temperature: float,
) -> str:
    client, model_id = make_client(model_name)
    resp = client.chat.completions.create(
        model=model_id,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content


def _postprocess_to_list(text: str) -> List[Dict[str, str]]:
    """
    Accept model output that *should* be valid JSON but may be wrapped in
    fenced code blocks. Extract the first fenced JSON if present, else parse raw.
    """
    s = (text or "").strip()
    # Prefer ```json ... ``` or ``` ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, flags=re.IGNORECASE)
    if m:
        s = m.group(1).strip()
    return json.loads(s)


def _extract_for_paragraph(
    paragraph: str,
    *,
    system_prompt: str,
    model_name: str,
    temperature: float,
) -> List[Dict[str, str]]:
    """
    Extract minimal claims for one *paragraph* (string) → list[dict].
    """
    raw = _chat_completion(
        prompt=paragraph,
        system_prompt=system_prompt,
        model_name=model_name,
        temperature=temperature,
    )
    return _postprocess_to_list(raw)


async def _achat_completion(
    prompt: str, system_prompt: str, model_name: str, temperature: float = 0.01
) -> str:
    client, model_id = make_async_client(model_name)
    try:
        async for attempt in AsyncRetrying(
            wait=wait_random_exponential(multiplier=1, max=20),
            stop=stop_after_attempt(6),
            retry=retry_if_exception_type(openai.OpenAIError),
        ):
            with attempt:
                resp = await client.chat.completions.create(
                    model=model_id,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                )
                return resp.choices[0].message.content
    finally:
        try:
            closer = getattr(client, "aclose", None) or getattr(client, "close", None)
            if closer:
                res = closer()
                if asyncio.iscoroutine(res):
                    await res
        except Exception:
            pass


async def _extract_for_paragraph_async(
    text: str, *, system_prompt: str, model_name: str, temperature: float
) -> list[dict[str, str]]:
    raw = await _achat_completion(text, system_prompt, model_name, temperature)
    return _postprocess_to_list(raw)


async def run_claim_extraction_async(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    model_name: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    max_concurrency: int = 8,
) -> Path:
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.with_name(f"{input_path.stem}_claims.json")
    output_path = Path(output_path)

    system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    max_concurrency = max_concurrency or LLM_MAX_PARALLEL

    data = json.loads(input_path.read_text(encoding="utf-8"))
    sem = asyncio.Semaphore(int(max(1, max_concurrency)))

    async def worker(idx: int, rec: dict) -> Tuple[int, dict]:
        try:
            async with sem:
                t1 = _extract_for_paragraph_async(
                    rec.get("paragraph_1", ""),
                    system_prompt=system_prompt,
                    model_name=model_name,
                    temperature=temperature,
                )
                t2 = _extract_for_paragraph_async(
                    rec.get("paragraph_2", ""),
                    system_prompt=system_prompt,
                    model_name=model_name,
                    temperature=temperature,
                )
                out1, out2 = await asyncio.gather(t1, t2)
            rec = dict(rec)
            rec["output_1"] = out1
            rec["output_2"] = out2
            rec["similarity"] = rec.get("similarity", 0.0)
            return idx, rec
        except Exception as exc:
            rec = dict(rec)
            rec["output_1"] = None
            rec["output_2"] = None
            rec["similarity"] = None
            rec["error"] = str(exc)
            return idx, rec

    tasks = [asyncio.create_task(worker(i, r)) for i, r in enumerate(data)]
    results = await asyncio.gather(*tasks)
    out = [None] * len(results)
    for idx, r in results:
        out[idx] = r
    out = [r for r in out if r is not None]
    output_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path
