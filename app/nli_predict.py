from pathlib import Path
from typing import List

import gradio as gr
from lettucedetect.models.inference import HallucinationDetector

from app.settings import side_bar


#  Config
EXTRA_CSS = side_bar

# Base directory where the NLI transformer models are stored.
MODEL_BASE = (Path(__file__).resolve().parent.parent / "nli" / "output").resolve()
if not MODEL_BASE.exists():
    MODEL_BASE = (Path(__file__).resolve().parent / "output").resolve()

CLASS_LABELS = {0: "neutral", 1: "contradiction", 2: "entailment"}
# Cache loaded detectors to avoid re‑loading on every click
_detectors = {}


def _list_models() -> List[str]:
    """Return sorted list of available model directories inside *MODEL_BASE*."""
    if not MODEL_BASE.exists():
        return []
    return sorted(p.name for p in MODEL_BASE.iterdir() if p.is_dir())


def _get_detector(model_name: str) -> HallucinationDetector:
    """Lazy‑load a ``HallucinationDetector`` for *model_name* and cache it."""
    if model_name not in _detectors:
        model_path = MODEL_BASE / model_name
        if not model_path.exists():
            raise FileNotFoundError(f"Model path not found: {model_path}")
        _detectors[model_name] = HallucinationDetector(
            method="transformer", model_path=str(model_path)
        )
    return _detectors[model_name]



def run_nli(model_name: str, claim: str, paragraph: str):
    """Predict the NLI relation between *claim* and *paragraph*."""
    if not model_name:
        return {"error": "Please choose a model."}

    detector = _get_detector(model_name)
    predictions = detector.predict_prompt(
        prompt=claim, answer=paragraph, output_format="spans"
    )

    # Map numeric labels → human‑readable strings
    for pred in predictions:
        pred["type"] = CLASS_LABELS.get(pred.get("label", 0))
    return predictions


with gr.Blocks(css=EXTRA_CSS) as demo:
    gr.Markdown("## NLI Predictor")

    # sidebar nav
    gr.HTML(
        """
        <div id="sidebar">
            <a href="/">Pipeline</a>
            <a href="/mismatch/">Mismatch</a>
            <a href="/nli/">NLI Viewer</a>
            <a href="/nli-predict/">NLI Predict</a>
        </div>
        """,
        visible=True,
    )

    # input widgets
    with gr.Row():
        model_dd = gr.Dropdown(
            label="Model",
            choices=_list_models(),
            value=_list_models()[0] if _list_models() else None,
            interactive=True,
        )

    claim_tb = gr.Textbox(label="Claim", lines=2, placeholder="Введите утверждение…")
    paragraph_tb = gr.Textbox(
        label="Paragraph / Answer",
        lines=4,
        placeholder="Введите абзац / ответ…",
    )

    run_btn = gr.Button("Run NLI")
    result_json = gr.JSON(label="Predictions (spans)")

    run_btn.click(
        run_nli, inputs=[model_dd, claim_tb, paragraph_tb], outputs=result_json
    )


if __name__ == "__main__":
    demo.launch()
