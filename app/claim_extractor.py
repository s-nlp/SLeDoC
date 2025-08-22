from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import openai
from dotenv import load_dotenv
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)
from tqdm import tqdm

from app.openai_client import make_client

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


# ──────────────────────────────────────────────────────────────────────────────
# Low-level OpenAI wrapper with basic exponential-back-off
# ──────────────────────────────────────────────────────────────────────────────
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


# ──────────────────────────────────────────────────────────────────────────────
# Public helper for a whole JSON file
# ──────────────────────────────────────────────────────────────────────────────
def run_claim_extraction(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    model_name: str = "gpt-4o",
    temperature: float = 0.2,
) -> Path:
    """Extract claims for every ``{"paragraph_1", "paragraph_2"}`` record in
    *input_path* and write a sibling file suffixed with ``_claims``.

    The function **automatically** chooses the right API endpoint depending on
    ``model_name`` (see top of this file).
    """

    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.with_name(
            f"{input_path.stem}_claims{input_path.suffix}"
        )
    output_path = Path(output_path)

    with input_path.open("r", encoding="utf-8") as f:
        data: List[Dict[str, Any]] = json.load(f)

    for rec in tqdm(data, desc="Extracting claims", ncols=88):
        try:
            rec["output_1"] = _extract_for_paragraph(
                rec["paragraph_1"],
                system_prompt=system_prompt,
                model_name=model_name,
                temperature=temperature,
            )
            rec["output_2"] = _extract_for_paragraph(
                rec["paragraph_2"],
                system_prompt=system_prompt,
                model_name=model_name,
                temperature=temperature,
            )
            # Whatever your similarity placeholder was ↓
            rec["similarity"] = rec.get("similarity", 0.0)
        except Exception as exc:
            # Keep batch going – mark failures for later inspection
            rec["output_1"] = None
            rec["output_2"] = None
            rec["similarity"] = None
            rec["error"] = str(exc)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return output_path
