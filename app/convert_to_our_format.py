import ast
import json
import tempfile
from pathlib import Path
from typing import Dict, List

import gradio as gr
import pandas as pd

from .settings import SIDEBAR_CSS, nav_tag

LABEL_MAP_DEFAULT = {
    "equivalent": "entailment",
    "contradiction": "contradiction",
    "addition": "neutral",
}


def _safe_literal_eval(x):
    try:
        return ast.literal_eval(x)
    except Exception:
        try:
            if isinstance(x, list):
                return x
            return json.loads(x)
        except Exception:
            return []


def convert_csv_to_nli_json(
    csv_file: str | Path,
    label_map: Dict[str, str] | None = None,
    keep_reasoning: bool = True,
) -> List[dict]:
    """
    Read CSV with columns ['paragraph_1','paragraph_2','output'] and
    produce a list of dicts in our NLI container format:
      {
        "input_1": <full paragraph_1>,
        "input_2": <full paragraph_2>,
        "output_1": [{"input": <span_1>, "claim": <span_1>}, ...],
        "output_2": [{"input": <span_2>, "claim": <span_2>}, ...],
        "nli_results": [
            {
              "premise": <span_1>,
              "hypothesis": <span_2>,
              "premise_raw": <span_1>,
              "hypothesis_raw": <span_2>,
              "label": <entailment|contradiction|neutral>,
              "confidence": null,
              "explanation": <reasoning?>,
            },
            ...
        ],
        "nli_model": "converted_from_csv"
      }
    """
    label_map = label_map or LABEL_MAP_DEFAULT
    df = pd.read_csv(csv_file)

    out: List[dict] = []
    for _, row in df.iterrows():
        p1 = str(row.get("paragraph_1", "") or "")
        p2 = str(row.get("paragraph_2", "") or "")
        raw = _safe_literal_eval(row.get("output", "[]"))

        spans1, spans2 = [], []
        seen1, seen2 = set(), set()

        nli_results = []
        for item in raw or []:
            s1 = str(item.get("span_1", "") or "").strip()
            s2 = str(item.get("span_2", "") or "").strip()
            lab = str(item.get("label", "") or "").strip().lower()
            mapped = label_map.get(lab, "neutral")

            if s1 and s1 not in seen1:
                spans1.append({"input": s1, "claim": s1})
                seen1.add(s1)
            if s2 and s2 not in seen2:
                spans2.append({"input": s2, "claim": s2})
                seen2.add(s2)

            res = {
                "premise": s1,
                "hypothesis": s2,
                "premise_raw": s1,
                "hypothesis_raw": s2,
                "label": mapped,
                "confidence": None,
            }
            if item.get("anchor"):
                res["anchor"] = str(item["anchor"])
            if keep_reasoning and item.get("reasoning"):
                res["explanation"] = str(item["reasoning"])
            nli_results.append(res)

        out.append(
            {
                "input_1": p1,
                "input_2": p2,
                "output_1": spans1,
                "output_2": spans2,
                "nli_results": nli_results,
                "nli_model": "converted_from_csv",
            }
        )
    return out


def _parse_label_map(text: str) -> Dict[str, str]:
    text = (text or "").strip()
    if not text:
        return LABEL_MAP_DEFAULT.copy()
    # Expect "equivalent=entailment, contradiction=contradiction, addition=neutral"
    pairs = [p.strip() for p in text.split(",")]
    out = {}
    for p in pairs:
        if "=" in p:
            k, v = [t.strip() for t in p.split("=", 1)]
            if k and v:
                out[k] = v
    return out or LABEL_MAP_DEFAULT.copy()


def _convert_tmp(csv_file, label_map_text, keep_reasoning):
    if not csv_file:
        raise gr.Error("Please upload a CSV file.")
    lm = _parse_label_map(label_map_text)
    result = convert_csv_to_nli_json(
        csv_file.name if hasattr(csv_file, "name") else csv_file,
        lm,
        keep_reasoning,
    )

    # Write to a writable temp directory (works even if app root is read-only)
    tmp_dir = Path(tempfile.mkdtemp(prefix="nli_convert_"))
    fname = f"converted_{Path(csv_file.name).stem}.json"
    out_path = tmp_dir / fname
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    preview_text = json.dumps(result[:2], ensure_ascii=False, indent=2)

    # Your Gradio version's DownloadButton expects a *path* string, not bytes/BytesIO
    return gr.update(value=str(out_path), visible=True), preview_text


def build_demo():
    with gr.Blocks(
        title="Convert CSV → NLI JSON", css=SIDEBAR_CSS, theme=gr.themes.Soft()
    ) as demo:
        gr.HTML(nav_tag)
        gr.Markdown(
            "### CSV → Our NLI format\n"
            "Upload a CSV with columns **paragraph_1**, **paragraph_2**, and **output** "
            "(list of dicts with span_1/span_2/label[, reasoning])."
        )
        with gr.Row():
            csv_in = gr.File(
                label="Upload CSV", file_count="single", file_types=[".csv"]
            )
        with gr.Accordion("Advanced", open=False):
            label_map_text = gr.Textbox(
                label="Label mapping (CSV→NLI)",
                value="equivalent=entailment, contradiction=contradiction, addition=neutral",
            )
            keep_reasoning = gr.Checkbox(
                value=True, label="Keep 'reasoning' in output as 'explanation'"
            )
        convert_btn = gr.Button("Convert", variant="primary")

        # DownloadButton (expects a *file path* on your Gradio version)
        download = gr.DownloadButton(label="Download converted JSON", visible=False)
        preview = gr.Code(label="Preview (first 2 items)", language="json")

        convert_btn.click(
            _convert_tmp,
            inputs=[csv_in, label_map_text, keep_reasoning],
            outputs=[download, preview],
        )
    return demo


demo = build_demo()
