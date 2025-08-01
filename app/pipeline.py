import os
import io
import json
from datetime import datetime as dt
from pathlib import Path

import gradio as gr
import pandas as pd

from app.clame_extractor import DEFAULT_SYSTEM_PROMPT, run_claim_extraction

from app.nli_predict import demo as nli_predict_demo
from app.combine_pairs import demo as combine_demo

from .settings import nav_tag, side_bar

EXTRA_CSS = side_bar
OPENAI_MODELS = ["gpt-4o", "gpt-3.5-turbo-0125"]
OPENROUTER_MODELS = [
    "openrouter/mistral-7b",
    "openrouter/meta-llama-3-70b-instruct",
    "openrouter/mistralai-mistral-8x22b",
]


def ui_run_claims(in_file, sys_prompt, model_name, temperature, use_env, api_key):
    if in_file is None:
        raise gr.Error("Please upload a .json file first.")

    key_arg = None if use_env else api_key

    out_path = run_claim_extraction(
        input_path=in_file.name,
        # api_key=key_arg,
        system_prompt=sys_prompt,
        model_name=model_name,
        temperature=temperature,
    )

    # ✅  Cast Path to str so gr.File can serialise it
    return str(out_path)


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
        with gr.Tab("💬 1. Extract claims"):
            in_file = gr.File(
                label="JSON with paragraph_1 / paragraph_2",
                file_types=[".json"],
            )
            model_dd = gr.Dropdown(
                label="Model",
                choices=OPENAI_MODELS + OPENROUTER_MODELS,
                value=os.getenv("DEFAULT_MODEL", OPENAI_MODELS[0]),
                interactive=True,
            )
            sys_prompt_box = gr.Textbox(
                label="System Prompt",
                value=DEFAULT_SYSTEM_PROMPT,
                lines=12,
            )
            # model_name_box = gr.Textbox(label="OpenAI model", value="gpt-4o")
            temp_slider = gr.Slider(0.0, 1.0, value=0.2, step=0.01, label="Temperature")

            # ── NEW: choose where the key comes from ──────────────────────────────────
            use_env_key = gr.Checkbox(
                label="Use $OPENAI_API_KEY from environment / .env",
                value=True,
            )
            api_key_box = gr.Textbox(
                label="OpenAI API key (only if not using env)",
                type="password",
                visible=False,  # start hidden
                placeholder="sk-...",
            )

            def _toggle(v):  # v == True  → hide textbox
                return gr.update(visible=not v)

            use_env_key.change(_toggle, use_env_key, api_key_box)
            # ─────────────────────────────────────────────────────────────────────────

            with gr.Row():
                run_btn = gr.Button(
                    "Extract", scale=1
                )  # scale expands in the flex-box row
            out_file = gr.File(label="⇩ Enriched JSON")

            run_btn.click(
                fn=ui_run_claims,
                inputs=[
                    in_file,
                    sys_prompt_box,
                    model_dd,
                    temp_slider,
                    use_env_key,
                    api_key_box,
                ],
                outputs=out_file,
            )

        # 3-b · NLI tab ------------------------------------------------------
        with gr.Tab("2. Compute NLI"):
            nli_predict_demo.render()
        # 🆕 Stage-3 tab
        with gr.Tab("3. Build final text"):
            combine_demo.render()

if __name__ == "__main__":
    demo.queue(concurrency_count=4).launch(
        show_error=True,
    )
