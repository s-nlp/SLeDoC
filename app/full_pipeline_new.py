from __future__ import annotations

import html
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
from app.claim_extractor import DEFAULT_SYSTEM_PROMPT, run_claim_extraction

# Stage 2
from app.nli_predict import _list_models, run_nli_file

# Stage 1+2 via LLM
from app.pipeline_llm import SYSTEM_PROMPT as LLM_NLI_SYSTEM_PROMPT
from app.pipeline_llm import run_llm_nli_file

# Shared UI assets
from app.settings import CUSTOM_JS, EXTRA_CSS, nav_tag, side_bar

# ----------------------------- Styling -----------------------------
EXTRA_CSS = (
    EXTRA_CSS
    + side_bar
    + """
/* dual-pane viewer layout */
.viewer-wrap { display:flex; gap:16px; align-items:flex-start; }
.left-pane  { flex: 2 1 0; min-width: 420px; }
.right-pane { flex: 1 1 0; position:sticky; top:10px; max-height:78vh; overflow:auto; }

/* paragraph card */
.para-box{
  border:1px solid #adb5bd; padding:12px; border-radius:12px;
  margin:12px 0; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.05);
}
.para-head { font-size:12px; color:#667085; margin-bottom:6px; }

/* claim spans */
.hl{ position:relative; padding:0 3px; border-radius:5px; cursor:pointer; }
.hl:hover { outline:1px dashed #888; }

/* NLI colors — keep them faint */
.hl.entailment     { background: rgba(34,197,94,.18); }   /* green */
.hl.neutral        { background: rgba(59,130,246,.18); }  /* blue */
.hl.contradiction  { background: rgba(244,63,94,.18); }   /* red */

/* selected state: strong outline, keep original background color */
.hl.selected { outline:2px solid #000 !important; }

/* mute tooltip artifacts */
.hl::after { display:none !important; }

/* right mirror */
.mirror-box{
  border:1px solid #adb5bd; padding:12px; border-radius:12px; background:#fafafa;
  min-height:140px;
}
"""
)


# ----------------------------- Helpers -----------------------------
def _escape(s: str) -> str:
    return html.escape(s or "", quote=False).replace("\n", "<br>")


def _safe_get(p: Dict[str, Any], keys: List[str]) -> str:
    for k in keys:
        v = p.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _text_left(p: Dict[str, Any]) -> str:
    return _safe_get(
        p,
        ["premise_raw", "premise", "paragraph_1", "input_1", "text_left", "left", "a"],
    )


def _text_right(p: Dict[str, Any]) -> str:
    return _safe_get(
        p,
        [
            "hypothesis_raw",
            "hypothesis",
            "paragraph_2",
            "input_2",
            "text_right",
            "right",
            "b",
        ],
    )


def _index_claims(claims: List[Dict[str, Any]]) -> Dict[str, int]:
    """Map claim text -> index for quick lookup."""
    idx = {}
    if not isinstance(claims, list):
        return idx
    for i, c in enumerate(claims):
        s = str(c.get("claim") or c.get("input") or "").strip()
        if s:
            idx[s] = i
    return idx


def _link_map_for_pair(
    block: Dict[str, Any],
) -> Tuple[Dict[int, List[Tuple[int, str]]], Dict[int, str]]:
    """
    Build:
      - links: left_idx -> list of (right_idx, label)
      - left_color: left_idx -> 'contradiction'|'neutral'|'entailment' (worst label if multiple)
    Works with string-based nli_results as produced by run_nli_file / run_llm_nli_file.
    """
    out_links: Dict[int, List[Tuple[int, str]]] = {}
    left_color: Dict[int, str] = {}

    out1 = block.get("output_1") or []
    out2 = block.get("output_2") or []
    idx1 = _index_claims(out1)
    idx2 = _index_claims(out2)

    # severity order
    sev = {"contradiction": 3, "neutral": 2, "entailment": 1}

    for r in block.get("nli_results") or []:
        prem = str(r.get("premise_raw") or r.get("premise") or "")
        hyp = str(r.get("hypothesis_raw") or r.get("hypothesis") or "")
        lbl = str(r.get("label") or "").lower()

        i_left: Optional[int] = None
        i_right: Optional[int] = None

        # case A: premise on left, hypothesis on right
        if prem in idx1 and hyp in idx2:
            i_left = idx1[prem]
            i_right = idx2[hyp]

        # case B: swapped
        elif prem in idx2 and hyp in idx1:
            i_left = idx1[hyp]
            i_right = idx2[prem]

        if i_left is None or i_right is None:
            continue

        out_links.setdefault(i_left, []).append((i_right, lbl))
        # update left color to "worst" severity among links
        cur = left_color.get(i_left)
        if cur is None or sev.get(lbl, 0) > sev.get(cur, 0):
            left_color[i_left] = lbl

    return out_links, left_color


# ----------------------------- Renderers -----------------------------
_BRIDGE_JS = r"""
<script>
(function(){
  function emitBridge(val){
    const el = document.querySelector('#bridge_click textarea');
    if (!el) return;
    el.value = val;
    el.dispatchEvent(new Event('input', {bubbles:true}));
  }
  // paragraph clicks (on card background)
  document.querySelectorAll('.para-box').forEach(function(box){
    const idx = box.getAttribute('data-idx');
    box.addEventListener('click', function(e){
      if (e.target && e.target.classList.contains('hl')) return;
      emitBridge('P:'+idx);
    });
  });
  // claim span clicks
  document.querySelectorAll('.hl').forEach(function(span){
    span.addEventListener('click', function(e){
      e.stopPropagation();
      // local selection visuals (non-authoritative)
      document.querySelectorAll('.hl.selected').forEach(el=>el.classList.remove('selected'));
      span.classList.add('selected');
      const pidx = span.getAttribute('data-pair');
      const lidx = span.getAttribute('data-left');
      emitBridge('S:'+pidx+':'+lidx);
    });
  });
})();
</script>
"""


def _render_left(blocks: List[Dict[str, Any]]) -> str:
    """
    Big left pane: for each pair, show Document A claims as spans, colored by worst NLI link.
    If no claims available for a block, fall back to raw paragraph text.
    """
    html_parts = ['<div class="viewer-wrap"><div class="left-pane">']
    for pi, b in enumerate(blocks):
        out1 = b.get("output_1") or []
        links, left_color = _link_map_for_pair(b)

        if out1:
            spans = []
            for i1, c in enumerate(out1):
                txt = _escape(c.get("claim") or c.get("input") or "")
                cls = "hl " + (left_color.get(i1, "") or "")
                spans.append(
                    f'<span class="{cls}" data-pair="{pi}" data-left="{i1}">{txt}</span>'
                )
            inner = "<br>".join(spans)
        else:
            inner = _escape(_text_left(b))

        html_parts.append(
            f"""
          <div class="para-box" data-idx="{pi}">
            <div class="para-head">Document A — paragraph {pi+1}</div>
            <div>{inner}</div>
          </div>
        """
        )

    html_parts.append("</div>")  # left-pane
    html_parts.append('<div class="right-pane"><div id="right-mirror"></div></div>')
    html_parts.append("</div>")  # viewer-wrap
    html_parts.append(_BRIDGE_JS)
    return "\n".join(html_parts)


def _render_right(
    blocks: List[Dict[str, Any]], focus: Tuple[int, Optional[int]]
) -> str:
    """
    Small right pane:
      - If focus=(k, None): show all right claims for block k.
      - If focus=(k, i_left): show only right claims linked to that left claim, colored by their labels.
        If multiple left claims link to the same right claim with different labels, choose worst.
    """
    k, i_left = focus
    if not (0 <= k < len(blocks)):
        return '<div class="mirror-box">—</div>'

    b = blocks[k]
    out2 = b.get("output_2") or []
    links, _left_color = _link_map_for_pair(b)

    # choose right-side coloring
    label_for_right: Dict[int, str] = {}
    severity = {"contradiction": 3, "neutral": 2, "entailment": 1}
    if i_left is None:
        # aggregate across all left links to compute worst label per right claim
        for li, pairs in links.items():
            for rj, lbl in pairs:
                if severity.get(lbl, 0) > severity.get(label_for_right.get(rj, ""), 0):
                    label_for_right[rj] = lbl
        show_indices = (
            sorted(label_for_right.keys())
            if label_for_right
            else list(range(len(out2)))
        )
    else:
        for rj, lbl in links.get(i_left, []):
            if severity.get(lbl, 0) > severity.get(label_for_right.get(rj, ""), 0):
                label_for_right[rj] = lbl
        show_indices = sorted(label_for_right.keys())

    # build HTML
    if show_indices:
        spans = []
        for j in show_indices:
            c = out2[j]
            txt = _escape(c.get("claim") or c.get("input") or "")
            cls = "hl " + (label_for_right.get(j, "") or "")
            spans.append(
                f'<span class="{cls}" data-pair="{k}" data-right="{j}">{txt}</span>'
            )
        body = "<br>".join(spans)
    else:
        body = _escape(_text_right(b))

    return f"""
      <div class="mirror-box">
        <div class="para-head">Document B — {'matching claims' if i_left is not None else 'aligned paragraph'} (pair {k+1})</div>
        <div>{body}</div>
      </div>
    """


# ----------------------------- Pipeline -----------------------------
def _align_stage0(
    doc1,
    doc2,
    model_id: str,
    device: str,
    batch_size: int,
    window_size: int,
    threshold: float,
) -> Tuple[str, str]:
    """
    Returns (align_json_path, align_preview_json_str[:N]).
    """
    p1 = Path(doc1.name if hasattr(doc1, "name") else doc1)
    p2 = Path(doc2.name if hasattr(doc2, "name") else doc2)

    paragraphs_a = merge_incomplete_sentences(get_paragraphs_from_docx(p1))
    # For B you separated points & filtered Russian previously
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

    preview = json.dumps(data[:5], ensure_ascii=False, indent=2)
    return str(out_path), preview


def _orchestrate(
    doc1,
    doc2,
    use_llm_12: bool,
    nli_model_name: Optional[str],
    device: str,
    batch_size: int,
    window_size: int,
    threshold: float,
    claim_prompt: str,
):
    """
    Stage 0 -> (1+2 via LLM) or (1 then 2) -> render viewer.
    Returns:
      align_path, pairs_path, preview_json, left_html, right_html, pairs_list
    """
    align_path, _preview = _align_stage0(
        doc1,
        doc2,
        model_id="intfloat/multilingual-e5-base",
        device=device,
        batch_size=batch_size,
        window_size=window_size,
        threshold=threshold,
    )

    if use_llm_12:
        pairs_path = run_llm_nli_file(align_path, system_prompt=claim_prompt)
        pairs = json.loads(Path(pairs_path).read_text(encoding="utf-8"))
    else:
        # Stage 1
        claims_path = run_claim_extraction(align_path, system_prompt=claim_prompt)
        # Stage 2 (nli_predict.run_nli_file accepts (model_name, file_obj-or-path))
        nli_out_path = run_nli_file(
            nli_model_name or (_list_models()[0] if _list_models() else None),
            claims_path,
        )
        pairs_path = nli_out_path
        pairs = json.loads(Path(pairs_path).read_text(encoding="utf-8"))

    left_html = _render_left(pairs)
    right_html = _render_right(pairs, (0, None))

    return align_path, pairs_path, _preview, left_html, right_html, pairs


def _bridge_update(pairs: List[Dict[str, Any]], bridge_value: str) -> str:
    """
    bridge_value is:
      'P:<pair_idx>'               – paragraph selected
      'S:<pair_idx>:<left_claim>'  – specific left claim selected
    """
    try:
        if not bridge_value:
            return _render_right(pairs, (0, None))
        if bridge_value.startswith("P:"):
            k = int(bridge_value.split(":", 1)[1])
            return _render_right(pairs, (k, None))
        if bridge_value.startswith("S:"):
            _t, a, b = bridge_value.split(":")
            return _render_right(pairs, (int(a), int(b)))
    except Exception:
        pass
    return _render_right(pairs, (0, None))


# ----------------------------- UI -----------------------------
with gr.Blocks(
    css=EXTRA_CSS, js=CUSTOM_JS, title="Semantic Mismatch — Full Pipeline"
) as demo:
    # top nav + title
    gr.Markdown("## Full pipeline (dual-pane viewer)")
    gr.HTML(nav_tag, visible=True)

    with gr.Tabs():
        with gr.Tab("Full pipeline"):
            with gr.Row():
                with gr.Column(scale=3):
                    doc1 = gr.File(label="Document A (.docx)", file_types=[".docx"])
                    doc2 = gr.File(label="Document B (.docx)", file_types=[".docx"])

            with gr.Accordion("⚙️ Settings", open=False):
                with gr.Row():
                    use_llm_12 = gr.Checkbox(
                        value=True, label="Use combined Extract+NLI (LLM)"
                    )
                    llm_model = gr.Textbox(
                        value="gpt-4o-mini", label="LLM model (for combined 1+2)"
                    )
                with gr.Row():
                    nli_model = gr.Dropdown(
                        label="NLI model (when not using LLM 1+2)",
                        choices=_list_models(),
                        value=_list_models()[0] if _list_models() else None,
                    )
                    device = gr.Dropdown(
                        choices=["cpu", "cuda"], value="cpu", label="Device"
                    )
                with gr.Row():
                    batch_size = gr.Slider(
                        8, 128, value=64, step=8, label="Batch size (embed)"
                    )
                    window_size = gr.Slider(
                        5, 200, value=50, step=5, label="Window size (align)"
                    )
                    threshold = gr.Slider(
                        0.5, 0.99, value=0.90, step=0.01, label="Similarity threshold"
                    )
                with gr.Row():
                    claim_prompt = gr.Textbox(
                        value=LLM_NLI_SYSTEM_PROMPT or DEFAULT_SYSTEM_PROMPT,
                        lines=8,
                        label="Claim extraction system prompt",
                    )
                with gr.Row():
                    artifacts_json = gr.JSON(label="Artifacts", visible=False)

            run_btn = gr.Button("Run full pipeline", variant="primary")

            with gr.Row():
                left_html = gr.HTML(label="Document A (claims)", value="")
                right_html = gr.HTML(label="Document B (matches)", value="")
            # bridge for click events
            bridge_click = gr.Textbox(visible=False, elem_id="bridge_click")

            # hidden state
            pairs_state = gr.State([])
            align_path_state = gr.State("")
            pairs_path_state = gr.State("")

            with gr.Row():
                dl_pairs = gr.File(label="Download pairs.json", interactive=False)

            def _run(
                doc1_f,
                doc2_f,
                use_llm,
                nli_model_id,
                device_v,
                bs,
                win,
                thr,
                sys_prompt,
            ):
                (align_path, pairs_path, preview, left, right, pairs) = _orchestrate(
                    doc1_f,
                    doc2_f,
                    bool(use_llm),
                    nli_model_id,
                    device_v,
                    int(bs),
                    int(win),
                    float(thr),
                    sys_prompt,
                )
                return (
                    left,
                    right,
                    pairs,
                    align_path,
                    pairs_path,
                    gr.update(
                        value=json.loads(Path(align_path).read_text(encoding="utf-8")),
                        visible=False,
                    ),
                )

            run_btn.click(
                _run,
                inputs=[
                    doc1,
                    doc2,
                    use_llm_12,
                    nli_model,
                    device,
                    batch_size,
                    window_size,
                    threshold,
                    claim_prompt,
                ],
                outputs=[
                    left_html,
                    right_html,
                    pairs_state,
                    align_path_state,
                    pairs_path_state,
                    artifacts_json,
                ],
            )

            def _export(p):
                if not p:
                    return gr.update(visible=False)
                return gr.update(value=p, visible=True)

            run_btn.click(_export, inputs=pairs_path_state, outputs=dl_pairs)

            # connect bridge
            bridge_click.change(
                lambda ps, v: _bridge_update(ps or [], v or "P:0"),
                inputs=[pairs_state, bridge_click],
                outputs=right_html,
            )

# Fast launch guard
if __name__ == "__main__":
    demo.launch(show_error=True)
