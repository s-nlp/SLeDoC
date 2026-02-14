import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import gradio as gr
import openai
from tenacity import (
    AsyncRetrying,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from app.config import DEFAULT_MODEL, LLM_MAX_PARALLEL, LLM_NLI_SYSTEM_PROMPT
from app.convert_to_our_format import LABEL_MAP_DEFAULT
from app.openai_client import make_async_client, make_client
from app.settings import SIDEBAR_CSS, nav_tag


def _to_path(x: str | Path) -> Path:
    if isinstance(x, Path):
        return x
    return Path(str(x))


def run_llm_nli_file(
    input_path: str | Path,
    *,
    output_path: str | Path | None = None,
    system_prompt: str = "",
    model_name: str = DEFAULT_MODEL,
    temperature: float = 0.01,
    label_map: Dict[str, str] | None = None,
) -> Path:
    """Synchronous wrapper that delegates to async, keeping UI stable."""
    # Fallback order: UI -> ENV -> DEFAULT
    resolved_prompt = system_prompt or LLM_NLI_SYSTEM_PROMPT
    return asyncio.run(
        run_llm_nli_file_async(
            input_path,
            output_path=output_path,
            system_prompt=resolved_prompt,
            model_name=model_name,
            temperature=temperature,
            label_map=label_map,
            max_concurrency=LLM_MAX_PARALLEL,
        )
    )


# equivalent→entailment, contradiction→contradiction, addition→neutral
LABEL_MAP = LABEL_MAP_DEFAULT


def _as_path(obj) -> Path:
    if isinstance(obj, Path):
        return obj
    if isinstance(obj, dict):
        # handle gradio dict payloads
        p = obj.get("path") or obj.get("name")
        return Path(p) if p else Path(str(obj))
    return Path(getattr(obj, "name", obj))


# ─────────────────────────────────────────────────────────────────────────────
# LLM wrappers
@retry(
    wait=wait_random_exponential(multiplier=1, max=20),
    stop=stop_after_attempt(6),
    retry=retry_if_exception_type(openai.OpenAIError),
)
def _chat_completion(
    system_prompt: str, user_prompt: str, *, model_name: str, temperature: float
) -> str:
    client, model_id = make_client(model_name)
    resp = client.chat.completions.create(
        model=model_id,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return resp.choices[0].message.content


def _postprocess_to_list(text: str) -> List[Dict[str, Any]]:
    # Robustly strip optional code fences and parse JSON
    s = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, flags=re.IGNORECASE)
    if m:
        s = m.group(1).strip()
    return json.loads(s)


def _build_user_prompt(p1: str, p2: str) -> str:
    return f"Параграф 1: {p1}\n\nПараграф 2: {p2}"


def _llm_pairwise(
    p1: str, p2: str, *, system_prompt: str, model_name: str, temperature: float
) -> List[dict]:
    raw = _chat_completion(
        system_prompt,
        _build_user_prompt(p1, p2),
        model_name=model_name,
        temperature=temperature,
    )
    return _postprocess_to_list(raw)


def build_demo():
    with gr.Blocks(css=SIDEBAR_CSS, fill_height=True, title="Pipeline (LLM)") as demo:
        gr.HTML(nav_tag, visible=True)
        gr.Markdown("## Pipeline — LLM (Extract + NLI in one call)")
        with gr.Row():
            with gr.Column(scale=1):
                in_pairs = gr.File(
                    label="Upload pairs JSON from Stage 0 (`[{paragraph_1, paragraph_2, ...}, …]`)",
                    file_types=[".json"],
                    file_count="single",
                )
                model = gr.Textbox(
                    label="Model (OpenAI/OpenRouter id)", value=DEFAULT_MODEL
                )
                temp = gr.Slider(0.0, 1.0, value=0.2, step=0.05, label="Temperature")
                sys_prompt = gr.Textbox(
                    label="System prompt", value=LLM_NLI_SYSTEM_PROMPT, lines=12
                )
                run_btn = gr.Button("Run LLM (extract+NLI)", variant="primary")
                out_file = gr.File(label="Download NLI JSON", interactive=False)
                out_path_box = gr.Textbox(label="Saved to", interactive=False)
            with gr.Column(scale=1):
                preview = gr.Code(label="Preview (first item)", language="json")

        def _run(json_file, model_name, temperature, system_prompt):
            if not json_file:
                raise gr.Error("Upload pairs JSON first.")
            input_path = Path(
                json_file.name if hasattr(json_file, "name") else json_file
            )
            result_path = run_llm_nli_file(
                input_path,
                system_prompt=system_prompt,
                model_name=model_name,
                temperature=float(temperature),
            )
            data = json.loads(Path(result_path).read_text(encoding="utf-8"))
            prev = json.dumps(data[0] if data else {}, ensure_ascii=False, indent=2)
            return str(result_path), str(result_path), prev

        run_btn.click(
            _run,
            inputs=[in_pairs, model, temp, sys_prompt],
            outputs=[out_file, out_path_box, preview],
        )

    return demo


demo = build_demo()

if __name__ == "__main__":
    demo.queue(concurrency_count=4).launch(show_error=True)


async def _achat_completion(
    system_prompt: str, user_prompt: str, *, model_name: str, temperature: float
) -> str:
    client, model_id = make_async_client(model_name)
    try:
        # Tenacity async retry
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
                        {"role": "user", "content": user_prompt},
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


async def async_llm_pairwise(
    p1: str, p2: str, *, system_prompt: str, model_name: str, temperature: float
) -> list[dict]:
    user_prompt = _build_user_prompt(p1, p2)
    text = await _achat_completion(
        system_prompt, user_prompt, model_name=model_name, temperature=temperature
    )
    return _postprocess_to_list(text)


async def run_llm_nli_file_async(
    input_path: str | Path,
    *,
    output_path: str | Path | None = None,
    system_prompt: str = "",
    model_name: str = DEFAULT_MODEL,
    temperature: float = 0.01,
    label_map: Dict[str, str] | None = None,
    max_concurrency: int = 8,
) -> Path:
    resolved_prompt = system_prompt or LLM_NLI_SYSTEM_PROMPT
    input_path = _to_path(input_path)
    raw = input_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except Exception as e:
        raise ValueError(f"Cannot parse input JSON: {e}") from e
    if not isinstance(data, list):
        raise ValueError("Input must be a list of paragraph pairs.")
    if data and not isinstance(data[0], dict):
        raise ValueError(
            "Each element must be an object with 'paragraph_1'/'paragraph_2'."
        )

    if output_path is None:
        output_path = input_path.with_name(f"{input_path.stem}_llm_nli.json")
    output_path = _to_path(output_path)

    sem = asyncio.Semaphore(int(max(1, max_concurrency)))

    async def worker(idx: int, p1: str, p2: str) -> Tuple[int, dict]:
        try:
            async with sem:
                items = await async_llm_pairwise(
                    p1,
                    p2,
                    system_prompt=resolved_prompt,
                    model_name=model_name,
                    temperature=temperature,
                )
            # ── Pass 0: index left spans & compute "next left idx" per item ──
            n = len(items or [])
            left_idx_by_text: dict[str, int] = {}
            left_idx_for_item: list[int | None] = [None] * n
            for i, it in enumerate(items or []):
                s1 = str(it.get("span_1", "") or "").strip()
                if not s1:
                    continue
                if s1 not in left_idx_by_text:
                    left_idx_by_text[s1] = len(left_idx_by_text)
                left_idx_for_item[i] = left_idx_by_text[s1]
            next_left_idx_from: list[int | None] = [None] * n
            next_seen: int | None = None
            for i in range(n - 1, -1, -1):
                if left_idx_for_item[i] is not None:
                    next_seen = left_idx_for_item[i]
                next_left_idx_from[i] = next_seen

            # ── Pass 1: build outputs; anchor ADDITION to NEXT left span ──
            spans1, spans2 = [], []
            seen1, seen2 = set(), set()
            last_left_idx: int | None = None
            nli_results: List[dict] = []
            for i, it in enumerate(items or []):
                s1 = str(it.get("span_1", "") or "").strip()
                s2 = str(it.get("span_2", "") or "").strip()
                lab = str(it.get("label", "") or "").strip().lower()
                mapped = (label_map or {}).get(lab, None) or {
                    "equivalent": "entailment",
                    "contradiction": "contradiction",
                    "addition": "addition",
                }.get(lab, "neutral")

                if s1 and s1 not in seen1:
                    # keep stable position of left spans
                    left_pos = len(spans1)
                    left_idx_by_text[s1] = left_pos
                    spans1.append({"input": s1, "claim": s1})
                    seen1.add(s1)
                    last_left_idx = left_pos
                if s2 and s2 not in seen2:
                    spans2.append({"input": s2, "claim": s2})
                    seen2.add(s2)

                anchor_idx: int | None = None
                if mapped == "addition":
                    # 1) try explicit anchor phrase from the LLM
                    anc_txt = str(it.get("anchor") or "").strip()
                    if anc_txt and anc_txt in left_idx_by_text:
                        anchor_idx = left_idx_by_text[anc_txt]
                    # 2) if we have a left span text, use it
                    elif s1 and s1 in left_idx_by_text:
                        anchor_idx = left_idx_by_text[s1]
                    else:
                        # 3) prefer NEXT left span; fallback to previous
                        anchor_idx = next_left_idx_from[i]
                        if anchor_idx is None:
                            anchor_idx = last_left_idx

                res = {
                    "premise": s1,
                    "premise_raw": s1,
                    "hypothesis": s2,
                    "hypothesis_raw": s2,
                    "label": mapped,
                    "reasoning": it.get("reasoning") or "",
                }
                if anchor_idx is not None:
                    res["anchor"] = anchor_idx  # used by the viewer
                nli_results.append(res)
            rec = {
                "input_1": p1,
                "input_2": p2,
                "output_1": spans1,
                "output_2": spans2,
                "nli_results": nli_results,
                "nli_model": f"llm:{model_name}",
            }
            return idx, rec
        except Exception as exc:
            return idx, {
                "input_1": p1,
                "input_2": p2,
                "output_1": [],
                "output_2": [],
                "nli_results": [],
                "nli_model": f"llm:{model_name}",
                "error": str(exc),
            }

    tasks = []
    for i, rec in enumerate(data):
        p1 = str(rec.get("paragraph_1") or "")
        p2 = str(rec.get("paragraph_2") or "")
        tasks.append(asyncio.create_task(worker(i, p1, p2)))

    results = await asyncio.gather(*tasks)
    out = [None] * len(results)
    for idx, rec in results:
        out[idx] = rec
    # Fallback if something weird happened
    out = [r for r in out if r is not None]

    output_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path
