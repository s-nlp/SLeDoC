from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

import openai
from dotenv import load_dotenv
from tenacity import (
    AsyncRetrying,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from app.openai_client import make_async_client, make_client

os.environ["TOKENIZERS_PARALLELISM"] = "True"
load_dotenv()

default_api_key = os.getenv("OPENAI_API_KEY", "")
print(default_api_key)
if not default_api_key:
    raise ValueError(
        "OpenAI API key missing. Specify it in the UI or set "
        "OPENAI_API_KEY in your environment (e.g. via .env)."
    )


DEFAULT_SYSTEM_PROMPT = """Ты — юридический аналитик, который разбивает сложное юридическое предложение на минимальные смысловые единицы для подачи в модель Natural Language Inference (NLI).

Твоя задача – разбить входное предложение на минимальные самодостаточные утверждения, каждое из которых выражает законченную мысль.

Каждое утверждение должно быть:
- самодостаточным (не должно содержать местоимений и ссылок вроде "этот", "он", "такой")
- пригодным для подачи в NLI-модель
- грамматически корректным, юридически точным
- Для каждого утверждения укажи, из какого фрагмента исходного предложения оно получено (копируя ДОСЛОВНО участок текста, на котором оно основано).

Формат ответа:
[
  {
    "input": <Исходный кусок текста, скопированный дословно>,
    "claim": <Переписанное утверждение>
  }
]"""


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
    ```json … ``` or stray back-ticks and safely convert to Python.
    """
    cleaned = text.replace("```json", "").replace("```", "").replace("json", "").strip()
    return json.loads(cleaned)  # raises if still invalid → caught upstream


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


# Public helper for a whole JSON file
def run_claim_extraction(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    model_name: str = "gpt-4o",
    temperature: float = 0.2,
) -> Path:
    """Sync wrapper around `run_claim_extraction_async` enabling parallel LLM calls."""
    return asyncio.run(
        run_claim_extraction_async(
            input_path,
            output_path=output_path,
            system_prompt=system_prompt,
            model_name=model_name,
            temperature=temperature,
            max_concurrency=8,
        )
    )


async def _achat_completion(
    prompt: str, system_prompt: str, model_name: str, temperature: float
) -> str:
    client, model_id = make_async_client(model_name)
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
    model_name: str = "gpt-4o",
    temperature: float = 0.2,
    max_concurrency: int = 8,
) -> Path:
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.with_name(f"{input_path.stem}_claims.json")
    output_path = Path(output_path)

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
