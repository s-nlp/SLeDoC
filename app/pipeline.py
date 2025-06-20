import io
import json
from datetime import datetime as dt
from pathlib import Path

import gradio as gr
import pandas as pd

from .settings import side_bar, nav_tag

EXTRA_CSS = side_bar


# --------------------------------------------------------------------------
#  1 · Stage-1  :  Document → Claims-JSON
# --------------------------------------------------------------------------
def _get_bytes_and_name(file_obj):
    """
    Works for gradio.data_classes.NamedString, traditional TempFile,
    or a plain str path (useful in tests).
    Returns: (bytes, filename)
    """
    if hasattr(file_obj, "read"):  # TempFile
        return file_obj.read(), file_obj.name
    if hasattr(file_obj, "string"):  # NamedString (Gradio 5)
        return file_obj.string, file_obj.name
    if isinstance(file_obj, (str, Path)):
        with open(file_obj, "rb") as f:
            return f.read(), str(file_obj)
    raise ValueError("Unsupported file object type")


def fake_extract(file_obj):
    """Return [{paragraph_1, paragraph_2}, …] from .xlsx/.xls/.json."""
    raw, name = _get_bytes_and_name(file_obj)
    name = name.lower()

    # Excel ---------------------------------------------------------------
    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(raw))
        req = {"paragraph_1", "paragraph_2"}
        if not req <= set(df.columns):
            raise ValueError("Excel must contain columns: " + ", ".join(req))
        recs = df[list(req)].fillna("").to_dict("records")

    # JSON ----------------------------------------------------------------
    elif name.endswith(".json"):
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, list):
            recs = [
                {k: d.get(k, "") for k in ("paragraph_1", "paragraph_2")} for d in data
            ]
        elif isinstance(data, dict):
            recs = [
                {"paragraph_1": p1, "paragraph_2": p2}
                for p1, p2 in zip(
                    data.get("paragraph_1", []), data.get("paragraph_2", [])
                )
            ]
        else:
            raise ValueError("Unsupported JSON schema")
    else:
        raise ValueError("File must be .xlsx, .xls or .json")

    json_str = json.dumps(recs, ensure_ascii=False, indent=2)
    return recs, json_str


# --------------------------------------------------------------------------
#  2 · Stage-2  :  Claims-JSON + user input → NLI-JSON
# --------------------------------------------------------------------------
def make_dummy_nli(pars_json: str):
    """
    Convert pars.json (string) → nli.json with the bare minimum
    the NLI Gradio viewer expects.

    For each pair:
      • output_1 / output_2 : a single claim identical to the paragraph
      • nli_results         : one row, label alternates entailment / contradiction
    """
    pairs_in = json.loads(pars_json)
    pairs_out = []

    for idx, pr in enumerate(pairs_in):
        p1, p2 = pr["paragraph_1"], pr["paragraph_2"]

        # trivial “claims”
        out1 = [{"input": p1, "claim": p1}]
        out2 = [{"input": p2, "claim": p2}]

        # alternate labels just to have variety
        lab = "entailment" if idx % 2 == 0 else "contradiction"
        conf = 0.88 if lab == "entailment" else 0.42
        nli_r = [
            {
                "premise": p1,
                "hypothesis": p2,
                "premise_raw": p1,
                "hypothesis_raw": p2,
                "label": lab,
                "confidence": conf,
            }
        ]

        pairs_out.append(
            {
                "input_1": p1,
                "input_2": p2,
                "output_1": out1,
                "output_2": out2,
                "nli_results": nli_r,
                "nli_model": "dummy-pipeline",
                "similarity": 0.0,  # optional; viewer ignores if missing
            }
        )

    return {"generated_at": dt.utcnow().isoformat() + "Z", "pairs": pairs_out}


# --------------------------------------------------------------------------
#  3 · Build the UI (two Tabs)
# --------------------------------------------------------------------------
with gr.Blocks(css=EXTRA_CSS) as demo:
    gr.Markdown("## Main Pipeline")
    # ─ sidebar nav
    gr.HTML(nav_tag, visible=True)

    with gr.Tabs():
        # 3-a · Extraction tab ------------------------------------------------
        with gr.Tab("1. Extract claims"):
            in_file = gr.File(label="Upload document (.xlsx / .json)")
            run_btn = gr.Button("Run extraction")
            claims_js = gr.JSON(label="⟶ Claims / Inputs JSON")
            dl_btn = gr.DownloadButton(
                label="Download JSON",
                # file_name="pars.json",
                visible=True,
            )

            run_btn.click(
                lambda f: fake_extract(f) if f else (gr.update(), gr.update()),
                inputs=in_file,
                outputs=[claims_js, dl_btn],
            )

        # 3-b · NLI tab ------------------------------------------------------
        with gr.Tab("2. Compute NLI"):
            json_in = gr.Textbox(
                label="Paste claims JSON from step 1", lines=8, placeholder="[…]"
            )
            hypo_in = gr.Textbox(label="Hypothesis / second document", lines=3)
            nli_btn = gr.Button("Run NLI")
            nli_js = gr.JSON(label="⟶ NLI JSON")

            run_btn.click(
                lambda f: fake_extract(f) if f else gr.update(),
                inputs=in_file,
                outputs=claims_js,
            )
            nli_btn.click(
                lambda j, h: make_dummy_nli(j, h) if (j and h) else gr.update(),
                inputs=[json_in, hypo_in],
                outputs=nli_js,
            )

if __name__ == "__main__":
    demo.launch()
