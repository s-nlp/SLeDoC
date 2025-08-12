import json
from pathlib import Path

import gradio as gr

from app.align_docs import demo as align_demo
from app.claim_extractor import DEFAULT_SYSTEM_PROMPT, run_claim_extraction
from app.combine_pairs import demo as combine_demo
from app.nli_predict import demo as nli_predict_demo

from .settings import nav_tag, side_bar


def _save_json(obj, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def build_demo():
    with gr.Blocks(
        title="Semantic Mismatch · Pipeline", css=side_bar, theme=gr.themes.Soft()
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
                label="OpenAI model (env configured)", value="gpt-4o-mini"
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

        # Stage‑3 · Build final text
        with gr.Tab("3. Build final text"):
            combine_demo.render()

    return demo


demo = build_demo()

if __name__ == "__main__":
    demo.queue(concurrency_count=4).launch(show_error=True)
