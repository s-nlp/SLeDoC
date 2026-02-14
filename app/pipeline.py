import json
import os
from pathlib import Path

import gradio as gr

from app.align_docs import demo as align_demo
from app.claim_extractor import DEFAULT_SYSTEM_PROMPT, run_claim_extraction
from app.config import DEFAULT_MODEL
from app.combine_pairs import demo as combine_demo
from app.nli_predict import demo as nli_predict_demo
from app.pipeline_llm import LLM_NLI_SYSTEM_PROMPT, run_llm_nli_file
from app.settings import SIDEBAR_CSS, nav_tag


def _save_json(obj, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def _resolve_uploaded_path(file_obj) -> Path:
    """
    Normalize Gradio File input to a real on-disk Path with bytes present.
    Supports:
      - tempfile objects with .name
      - dicts with 'name' or 'path'
      - raw path strings
    Raises a ValueError with a helpful message if file is missing or empty.
    """
    candidate = None

    # 1) dict payload (gradio sometimes returns {'name': '/tmp/..', ...})
    if isinstance(file_obj, dict):
        candidate = file_obj.get("path") or file_obj.get("name")
    # 2) tempfile-like
    elif hasattr(file_obj, "name"):
        candidate = file_obj.name
    # 3) plain string path
    elif isinstance(file_obj, (str, os.PathLike)):
        candidate = str(file_obj)

    if not candidate:
        raise ValueError(
            "Не удалось определить путь к файлу (gr.File payload неизвестного типа)."
        )

    p = Path(candidate)
    if not p.exists():
        raise ValueError(f"Файл не найден: {p}")

    # Some environments create an empty placeholder next to a real file.
    # If the file is empty, try to follow a sibling 'file' entry if present.
    if p.is_file() and p.stat().st_size == 0:
        # Try common gradio temp conventions (e.g., .tmp, .json)
        # or embedded content key (rare). If still empty, fail early.
        raise ValueError(f"Загруженный файл пустой (0 байт): {p}")

    return p


def build_demo():
    with gr.Blocks(
        title="Semantic Mismatch · Pipeline", css=SIDEBAR_CSS, theme=gr.themes.Soft()
    ) as demo:
        gr.HTML(nav_tag)
        gr.Markdown("## Pipeline")

        # Stage‑0 · Align documents
        with gr.Tab("0. Align docs"):
            align_demo.render()

        # Stage‑1 · Claims extraction
        with gr.Tab("1. Extract claims"):
            in_pairs = gr.File(
                label="Upload pairs JSON (`[{paragraph_1, paragraph_2}, …]`)",
                file_types=[".json"],
                file_count="single",
            )
            sys_prompt = gr.Textbox(
                label="System prompt", value=DEFAULT_SYSTEM_PROMPT, lines=6
            )
            model = gr.Textbox(
                label="OpenAI/OpenRouter model (env configured)",
                value=DEFAULT_MODEL,
            )

            run_btn = gr.Button("Extract", variant="primary")
            download = gr.File(label="Download extracted JSON", interactive=False)
            out_path_box = gr.Textbox(label="Saved file", interactive=False)
            preview = gr.Code(label="Preview (first 2 items)", language="json")

            def _run_extract(json_file, system_prompt, model_name):
                if not json_file:
                    raise gr.Error("Upload pairs JSON first.")
                # Pass a path to run_claim_extraction (it expects a file path)
                input_path = Path(
                    json_file.name if hasattr(json_file, "name") else json_file
                )
                result_path = run_claim_extraction(
                    input_path, system_prompt=system_prompt, model_name=model_name
                )

                # Load first 2 items for preview
                data = json.loads(Path(result_path).read_text(encoding="utf-8"))
                preview_text = json.dumps(data[:2], ensure_ascii=False, indent=2)
                return str(result_path), str(result_path), preview_text

            run_btn.click(
                _run_extract,
                inputs=[in_pairs, sys_prompt, model],
                outputs=[download, out_path_box, preview],
            )

        # Stage‑2 · NLI
        with gr.Tab("2. Compute NLI"):
            nli_predict_demo.render()

        # Stage-1+2 · LLM (extract + NLI)
        with gr.Tab("1+2. LLM (Extract + NLI)"):
            in_pairs_12 = gr.File(
                label="Upload pairs JSON (`[{paragraph_1, paragraph_2}, …]`)",
                file_types=[".json"],
                file_count="single",
            )
            sys_prompt_12 = gr.Textbox(
                label="LLM (1+2) system prompt", value=LLM_NLI_SYSTEM_PROMPT, lines=10
            )
            model_12 = gr.Textbox(label="OpenAI/OpenRouter model", value=DEFAULT_MODEL)
            temp_12 = gr.Slider(0.0, 1.0, value=0.2, step=0.05, label="Temperature")

            run_btn_12 = gr.Button("Run LLM (extract+NLI)", variant="primary")
            download_12 = gr.File(label="Download NLI JSON", interactive=False)
            out_path_box_12 = gr.Textbox(label="Saved file", interactive=False)
            preview_12 = gr.Code(label="Preview (first 1 item)", language="json")

            def _run_llm_12(json_file, system_prompt, model_name, temperature):
                if not json_file:
                    raise gr.Error("Upload pairs JSON first.")

                try:
                    input_path = _resolve_uploaded_path(json_file)
                except Exception as e:
                    raise gr.Error(f"Ошибка чтения загруженного файла: {e}")

                # Validate JSON and expected structure early (helpful error if wrong file)
                try:
                    raw = input_path.read_text(encoding="utf-8")
                    if not raw.strip():
                        raise gr.Error(f"Загруженный файл пустой: {input_path}")
                    data = json.loads(raw)
                    if not isinstance(data, list):
                        raise gr.Error(
                            'Ожидался JSON-список пар. Пример: [{"paragraph_1": "...", "paragraph_2": "..."}, ...]'
                        )
                    # very light schema check
                    first = data[0] if data else {}
                    if not (
                        isinstance(first, dict)
                        and (("paragraph_1" in first) or ("p1" in first))
                    ):
                        # Allow your alternate keys if you use them internally
                        raise gr.Error(
                            "Каждый элемент должен иметь ключи 'paragraph_1' и 'paragraph_2'."
                        )
                except gr.Error:
                    raise
                except Exception as e:
                    raise gr.Error(f"Файл не является корректным JSON: {e}")

                # Run fused pipeline
                result_path = run_llm_nli_file(
                    input_path=input_path,
                    system_prompt=system_prompt,
                    model_name=model_name,
                    temperature=float(temperature),
                )

                data = json.loads(Path(result_path).read_text(encoding="utf-8"))
                preview_text = json.dumps(data[:1], ensure_ascii=False, indent=2)

                return str(result_path), str(result_path), preview_text

            run_btn_12.click(
                _run_llm_12,
                inputs=[in_pairs_12, sys_prompt_12, model_12, temp_12],
                outputs=[download_12, out_path_box_12, preview_12],
            )

        # Stage‑3 · Build final text
        with gr.Tab("3. Build final text"):
            combine_demo.render()

    return demo


demo = build_demo()

if __name__ == "__main__":
    demo.queue(concurrency_count=4).launch(show_error=True)
