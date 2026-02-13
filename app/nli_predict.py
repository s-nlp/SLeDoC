import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, List

import gradio as gr
from lettucedetect.models.inference import HallucinationDetector

from app.settings import SIDEBAR_CSS, nav_tag

#  Config
LOGLEVEL = (os.getenv("LOGLEVEL") or "INFO").upper()
logging.basicConfig(
    level=LOGLEVEL,
    format="%(levelname)s | %(name)s | %(message)s",
    force=True,
)
log = logging.getLogger(__name__)

EXTRA_CSS = SIDEBAR_CSS

# Base directory where the NLI transformer models are stored.
MODEL_BASE = (Path(__file__).resolve().parent.parent / "nli" / "output").resolve()
if not MODEL_BASE.exists():
    MODEL_BASE = (Path(__file__).resolve().parent / "output").resolve()

CLASS_LABELS = {0: "neutral", 1: "contradiction", 2: "entailment"}
_LABEL_TO_ID = {v: k for k, v in CLASS_LABELS.items()}

# Cache loaded detectors to avoid re‑loading on every click
_detectors = {}


def _span_conf(span: dict) -> float:
    """
    Return the numeric confidence of a model span.
    Different detector versions use slightly different keys – deal with all of
    them here so downstream code never breaks.
    """
    for k in (
        "confidence",
        "score",
        "scores",  # 🤗 transformers-style list of logits
        "conf",
        "prob",
        "probability",
    ):
        if k in span and span[k] is not None:
            v = span[k]
            # 'scores' can be a list → pick the max-probability logit
            if isinstance(v, (list, tuple)):
                v = max(v)
            return float(v)
    # if the span *is* a bare float already
    if isinstance(span, (float, int)):
        return float(span)
    return 0.0  # last-resort fallback


def _aggregate_span_predictions(raw) -> dict[str, float]:
    log.debug("RAW detector output: %s", raw)
    if raw is None:
        return {"label": 0, "confidence": 0.0}

    # 1) ready-made single verdict dict (no "spans" key)
    if isinstance(raw, dict) and "spans" not in raw:
        conf = _span_conf(raw)
        lbl = raw.get("label")
        if isinstance(lbl, str):
            lbl = _LABEL_TO_ID.get(lbl.lower(), 0)
        lbl = int(lbl or 0)
        return {"label": int(lbl), "confidence": float(conf)}

    # 2) wrapper dict – dig out the span list
    if isinstance(raw, dict) and "spans" in raw:
        raw = raw["spans"]  # fall through to case 3

    # 3) raw list of spans
    if not raw:  # empty list ⇒ default neutral, 0.0
        return {"label": 0, "confidence": 0.0}

    best = max(raw, key=_span_conf)

    log.debug("BEST span / verdict chosen: %s", best)
    if "label" in best:  # very old format
        label_id = int(best["label"])
    else:
        label_id = _LABEL_TO_ID.get(best.get("type", "neutral").lower(), 0)

    verdict = {"label": label_id, "confidence": float(_span_conf(best))}
    log.debug("Aggregated verdict: %s", verdict)
    return verdict


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


def _all_pairs(out1: List[Dict[str, str]], out2: List[Dict[str, str]]):
    """Cartesian product generator (premise × hypothesis)."""
    for p in out1:
        for h in out2:
            yield p, h


def _predict(detector, premise: str, hypothesis: str):
    """
    Wrapper that keeps asking the detector in different formats until we get a
    non-empty response.  It fixes the '[] ⇒ neutral/0' problem.
    """
    for fmt in ("spans", "tokens", "classification"):
        out = detector.predict_prompt(
            prompt=premise,
            answer=hypothesis,
            output_format=fmt,
        )
        if out:  # anything truthy → good enough
            return out
    return None  # give up


def run_nli_file(model_name: str, file_obj) -> str | None:
    """
    Read *pairs.json*, run the NLI model over every (claim, claim) pair,
    write **nli.json** to a temp-file and return its path so Gradio
    turns it into a downloadable link.
    """
    model_name = model_name or _list_models()[0]
    detector = _get_detector(model_name)
    print("DETECTOR", detector)
    raw = file_obj.read() if hasattr(file_obj, "read") else open(file_obj, "rb").read()
    pairs_in = json.loads(raw)

    pairs_out = []
    for block in pairs_in:
        nli_res = []
        for prem, hyp in _all_pairs(block["output_1"], block["output_2"]):
            predictions = _predict(
                detector,
                str(prem["claim"]),
                str(hyp["claim"]),
            )
            pred = _aggregate_span_predictions(predictions)

            nli_res.append(
                {
                    "premise": prem["input"],
                    "hypothesis": hyp["input"],
                    "premise_raw": prem["claim"],
                    "hypothesis_raw": hyp["claim"],
                    "label": CLASS_LABELS[pred["label"]],
                    "confidence": pred["confidence"],
                }
            )

        pairs_out.append(
            {
                "input_1": block["paragraph_1"],
                "input_2": block["paragraph_2"],
                "output_1": block["output_1"],
                "output_2": block["output_2"],
                "nli_results": nli_res,
                "nli_model": model_name,
            }
        )

    tmp = tempfile.NamedTemporaryFile(
        delete=False, suffix=".json", mode="w", encoding="utf-8"
    )
    json.dump(pairs_out, tmp, ensure_ascii=False, indent=2)
    tmp.close()
    return tmp.name


with gr.Blocks(css=EXTRA_CSS) as demo:
    gr.Markdown("## NLI Predictor")

    # sidebar nav
    gr.HTML(nav_tag, visible=True)

    # input widgets
    # two ways to run the model
    with gr.Tabs():
        # 2 · batch mode from file
        with gr.Tab("File"):
            with gr.Row():
                # model dropdown
                model_dd_batch = gr.Dropdown(
                    label="Model",
                    choices=_list_models(),
                    value=_list_models()[0] if _list_models() else None,
                    interactive=True,
                )
            file_in = gr.File(label="Upload pairs.json", file_types=[".json"])
            run_file_btn = gr.Button("Run NLI on file")
            file_out = gr.File(label="Download nli.json", interactive=False)
            run_file_btn.click(
                fn=run_nli_file,
                inputs=[model_dd_batch, file_in],
                outputs=[file_out],
            )

        # 1 · single pair
        with gr.Tab("Single pair"):
            with gr.Row():
                model_dd = gr.Dropdown(
                    label="Model",
                    choices=_list_models(),
                    value=_list_models()[0] if _list_models() else None,
                    interactive=True,
                )

                claim_tb = gr.Textbox(
                    label="Claim", lines=2, placeholder="Введите утверждение…"
                )
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
