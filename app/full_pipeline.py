import json
import tempfile
from pathlib import Path

import gradio as gr

# Stage 0
from app.align_docs import (
    Encoder,
    build_output_json,
    filter_non_russian,
    find_best_matches_with_window,
    get_paragraphs_from_docx,
    merge_incomplete_sentences,
    separate_points,
)

# Stage 1
from app.claim_extractor import run_claim_extraction

# Stage 3 building blocks
from app.combine_pairs import _preview_html, choose, download
from app.config import CLAIM_EXTRACTOR_SYSTEM_PROMPT as DEFAULT_SYSTEM_PROMPT
from app.config import DEFAULT_MODEL, LLM_NLI_SYSTEM_PROMPT

# Stage 2
from app.nli_predict import _list_models, run_nli_file

# Stage 1+2 with LLM
from app.pipeline_llm import run_llm_nli_file

from .settings import SIDEBAR_CSS, nav_tag


def _align_stage0(doc1, doc2, model_id, device, batch_size, window_size, threshold):
    p1 = Path(doc1.name if hasattr(doc1, "name") else doc1)
    p2 = Path(doc2.name if hasattr(doc2, "name") else doc2)

    paragraphs_a = merge_incomplete_sentences(get_paragraphs_from_docx(p1))
    paragraphs_b = filter_non_russian(
        separate_points(merge_incomplete_sentences(get_paragraphs_from_docx(p2)))
    )

    enc = Encoder.load(model_id=model_id, device=device)
    emb_a = enc.encode(paragraphs_a, batch_size=int(batch_size))
    emb_b = enc.encode(paragraphs_b, batch_size=int(batch_size))

    matches = find_best_matches_with_window(
        paragraphs=paragraphs_a,
        paragraphs_bi=paragraphs_b,
        paragraphs_embs=emb_a,
        paragraphs_bi_embs=emb_b,
        window_size=int(window_size),
        threshold=float(threshold),
    )

    data = build_output_json(paragraphs_a, paragraphs_b, matches)

    tmpdir = Path(tempfile.mkdtemp())
    out_path = tmpdir / "paragraphs_aligned.json"
    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    preview = (
        json.dumps(data[:5], ensure_ascii=False, indent=2)
        if isinstance(data, list)
        else ""
    )
    return str(out_path), preview


def _coerce_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)):
        return " ".join(_coerce_text(x) for x in v if x)
    if isinstance(v, dict):
        for k in ("text", "content", "value"):
            if k in v and v[k]:
                return _coerce_text(v[k])
        return " ".join(map(_coerce_text, v.values()))
    return str(v)


def _pick_side(p: dict, left: bool) -> str:
    left_keys = [
        "premise_raw",
        "premise",
        "claim_left",
        "text_left",
        "paragraph_1",
        "input_1",
        "output_1",
        "left",
        "a",
        "source_left",
    ]
    right_keys = [
        "hypothesis_raw",
        "hypothesis",
        "claim_right",
        "text_right",
        "paragraph_2",
        "input_2",
        "output_2",
        "right",
        "b",
        "source_right",
    ]
    for k in left_keys if left else right_keys:
        v = p.get(k)
        t = _coerce_text(v)
        if t and t.strip():
            return t.strip()
    return ""


def _normalize_pairs(pairs: list[dict]) -> list[dict]:
    norm = []
    for p in pairs:
        if not p.get("premise_raw"):
            p = {**p, "premise_raw": _pick_side(p, True)}
        if not p.get("hypothesis_raw"):
            p = {**p, "hypothesis_raw": _pick_side(p, False)}
        norm.append(p)
    return norm


def _safe_load_pairs(nli_json_path: str) -> list[dict]:
    with open(nli_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "pairs" in data:
        data = data["pairs"]
    return data if isinstance(data, list) else []


EXTRA_CSS = """
.progress-grid { display:grid; grid-template-columns: 28px 1fr; gap:10px; align-items:center; }
.stage-dot{ width:18px; height:18px; border-radius:99px; background:#777; }
.stage-dot.done{ background:#22c55e; }
.stage-dot.run{ background:#f59e0b; }
.stage-title{ font-weight:700; }

/* floating settings panel */
.floating-panel{
  position: fixed;
  right: 24px;
  top: 92px;
  width: 520px;
  max-height: 80vh;
  overflow: auto;
  z-index: 20;
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 10px 30px rgba(0,0,0,.12);
}
@media (max-width: 1280px) {
  .floating-panel { position: static; width: auto; max-height: none; box-shadow: none; }
}
"""


def _stage_status(stage: int) -> str:
    labels = [
        "0. Align docs",
        "1. Extract claims",
        "2. Compute NLI",
        "3. Build final text",
    ]
    html = ["<div class='progress-grid'>"]
    for i, lbl in enumerate(labels):
        cls = "stage-dot"
        if i < stage:
            cls += " done"
        elif i == stage:
            cls += " run"
        html.append(f"<div class='{cls}'></div><div class='stage-title'>{lbl}</div>")
    html.append("</div>")
    return "\n".join(html)


def _run_all(
    doc1,
    doc2,
    embed_model,
    device,
    batch_size,
    window_size,
    threshold,
    mode_12,
    system_prompt,
    llm_model,
    llm_temp,
    nli_model,
    progress=gr.Progress(track_tqdm=True),
):
    if not (doc1 and doc2):
        raise gr.Error("Please upload *both* .docx files.")

    out_path_align = ""
    claims_path = ""
    nli_json_path = ""
    progress_html = ""
    pairs = []
    idx0 = -1
    _ = set()
    _ = []
    label = "—"
    left = ""
    right = ""
    final_preview = ""

    progress(0.02, desc="Loading & encoding documents")
    out_path_align, _ = _align_stage0(
        doc1,
        doc2,
        embed_model,
        device,
        int(batch_size),
        int(window_size),
        float(threshold),
    )
    progress_html = _stage_status(1)

    yield (
        str(out_path_align),
        str(out_path_align),
        "",
        "",
        progress_html,
        [],
        -1,
        [],
        [],
        "—",
        "",
        "",
        "",
    )

    if str(mode_12).lower().startswith("llm"):
        progress(0.35, desc="LLM (1+2): extract + NLI")
        nli_json_path = run_llm_nli_file(
            input_path=out_path_align,
            system_prompt=system_prompt or LLM_NLI_SYSTEM_PROMPT,
            model_name=llm_model,
            temperature=float(llm_temp),
        )
        claims_path = ""
        progress_html = _stage_status(3)
    else:
        progress(0.35, desc="Extracting claims with LLM")
        claims_path = run_claim_extraction(
            input_path=out_path_align,
            system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT,
            model_name=llm_model,
            temperature=float(llm_temp),
        )
        progress_html = _stage_status(2)

        yield (
            str(out_path_align),
            str(out_path_align),
            str(claims_path),
            "",
            progress_html,
            [],
            -1,
            [],
            [],
            "—",
            "",
            "",
            "",
        )

        progress(0.65, desc="Running NLI over claim pairs")
        with open(claims_path, "rb") as f:
            nli_json_path = run_nli_file(nli_model, f)
        progress_html = _stage_status(3)

    raw_pairs = _safe_load_pairs(nli_json_path)
    pairs = _normalize_pairs(raw_pairs)

    print(
        f"[Combiner] pairs={len(pairs)}; keys0={list(pairs[0].keys()) if pairs else '—'}"
    )

    idx0 = 0 if pairs else -1
    label = "No aligned pairs" if idx0 == -1 else f"Ready • {len(pairs)} pairs"
    if idx0 != -1:
        p0 = pairs[idx0]
        left_raw = p0.get("premise_raw") or _pick_side(p0, True)
        right_raw = p0.get("hypothesis_raw") or _pick_side(p0, False)
        left = _preview_html(left_raw)
        right = _preview_html(right_raw)

    progress(0.98, desc="Ready")

    yield (
        str(out_path_align),
        str(out_path_align),
        str(claims_path),
        str(nli_json_path),
        progress_html,
        pairs,
        idx0,
        [],
        [],
        label,
        left,
        right,
        final_preview,
    )


with gr.Blocks(css=SIDEBAR_CSS + EXTRA_CSS, fill_height=True) as demo:
    gr.HTML(nav_tag)
    gr.Markdown("## Full Pipeline")

    with gr.Row():
        with gr.Column(scale=2):
            gr.Markdown("**Upload documents** (.docx)")
            doc1 = gr.File(label="Document A", file_types=[".docx"])
            doc2 = gr.File(label="Document B", file_types=[".docx"])

        with gr.Column(scale=1, min_width=260):
            settings_open = gr.State(False)
            settings_btn = gr.Button("⚙️ Settings", variant="secondary")
            run_btn = gr.Button("▶️ Run full pipeline", variant="primary")

    with gr.Column(visible=False, elem_classes=["floating-panel"]) as settings_panel:
        with gr.Accordion("Embedding settings", open=False):
            embed_model = gr.Dropdown(
                choices=[
                    "intfloat/multilingual-e5-large",
                    "intfloat/multilingual-e5-base",
                ],
                value="intfloat/multilingual-e5-base",
                label="Embedding model",
            )
            device = gr.Dropdown(choices=["cpu", "cuda"], value="cpu", label="Device")
            batch_size = gr.Slider(8, 128, value=64, step=8, label="Batch size")
            window_size = gr.Slider(5, 200, value=50, step=5, label="Window size")
            threshold = gr.Slider(
                0.5, 0.99, value=0.90, step=0.01, label="Similarity threshold"
            )
        with gr.Accordion("Claim extraction (LLM)", open=False):
            system_prompt = gr.Textbox(
                value=LLM_NLI_SYSTEM_PROMPT, label="System prompt", lines=10
            )
            llm_model = gr.Textbox(value=DEFAULT_MODEL, label="Model name")
            llm_temp = gr.Slider(0.0, 1.0, value=0.2, step=0.05, label="Temperature")
        with gr.Accordion("NLI model", open=False):
            nli_model = gr.Dropdown(
                label="Local NLI model",
                choices=_list_models(),
                value=_list_models()[0] if _list_models() else None,
            )
        with gr.Accordion("Stage 1+2 mode", open=True):
            mode_12 = gr.Radio(
                choices=["LLM (single-step)", "Not LLM (two-step)"],
                value="LLM (single-step)",
                label="How to run stages 1+2?",
            )
        with gr.Accordion("Artifacts", open=False):
            align_out_file = gr.File(label="Aligned JSON (download)", interactive=False)
            align_out = gr.Textbox(label="Aligned pairs JSON (path)", interactive=False)
            claims_out = gr.Textbox(label="Claims JSON (path)", interactive=False)
            nli_out = gr.Textbox(label="NLI JSON (path)", interactive=False)

    def _toggle_open(opened: bool):
        new_val = not bool(opened)
        return new_val, gr.update(visible=new_val)

    settings_btn.click(
        _toggle_open,
        inputs=[settings_open],
        outputs=[settings_open, settings_panel],
    )

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("**3. Build final text**")
            pairs_state = gr.State([])
            idx_state = gr.State(-1)
            seen_state = gr.State([])
            final_state = gr.State([])
            label_md = gr.Markdown("—")
            with gr.Row():
                left_html = gr.HTML("")
                right_html = gr.HTML("")
            with gr.Row():
                left_btn = gr.Button("⬅️ Choose left")
                skip_btn = gr.Button("Skip")
                right_btn = gr.Button("Choose right ➡️")
            final_preview = gr.Textbox(label="Accumulated text", lines=8)
            download_btn = gr.Button("⬇️ Download final text")
            download_file = gr.File(label="final_text.txt", interactive=False)

    gr.Markdown("---")
    gr.Markdown("**Progress**")
    progress_html = gr.HTML(_stage_status(0))

    run_btn.click(
        fn=_run_all,
        inputs=[
            doc1,
            doc2,
            embed_model,
            device,
            batch_size,
            window_size,
            threshold,
            mode_12,
            system_prompt,
            llm_model,
            llm_temp,
            nli_model,
        ],
        outputs=[
            align_out_file,
            align_out,
            claims_out,
            nli_out,
            progress_html,
            pairs_state,
            idx_state,
            seen_state,
            final_state,
            label_md,
            left_html,
            right_html,
            final_preview,
        ],
        show_progress=True,
    )

    def _wrap_choice(choice, pairs, idx, seen, final):
        return choose(choice, pairs, idx, seen, final)

    left_btn.click(
        _wrap_choice,
        inputs=[gr.State("left"), pairs_state, idx_state, seen_state, final_state],
        outputs=[
            label_md,
            left_html,
            right_html,
            final_preview,
            idx_state,
            seen_state,
            final_state,
        ],
    )
    right_btn.click(
        _wrap_choice,
        inputs=[gr.State("right"), pairs_state, idx_state, seen_state, final_state],
        outputs=[
            label_md,
            left_html,
            right_html,
            final_preview,
            idx_state,
            seen_state,
            final_state,
        ],
    )
    skip_btn.click(
        _wrap_choice,
        inputs=[gr.State("skip"), pairs_state, idx_state, seen_state, final_state],
        outputs=[
            label_md,
            left_html,
            right_html,
            final_preview,
            idx_state,
            seen_state,
            final_state,
        ],
    )

    download_btn.click(download, inputs=final_state, outputs=download_file)


if __name__ == "__main__":
    demo.queue(concurrency_count=2).launch(show_error=True)
