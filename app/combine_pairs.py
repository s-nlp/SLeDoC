import json
import tempfile
from pathlib import Path
from typing import List, Set, Tuple

import gradio as gr


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------
def _fmt_conf(x) -> str:
    """
    Safe formatter for confidence. Returns '—' if None/NaN/not-parsable.
    """
    try:
        if x is None:
            return "—"
        if isinstance(x, str):
            x = x.strip()
            if not x:
                return "—"
            x = float(x)
        v = float(x)
        if v != v:  # NaN check
            return "—"
        return f"{v:.3f}"
    except Exception:
        return "—"


def _flatten_nli_container(obj) -> List[dict]:
    """Return a flat list of NLI pair‑dicts from *obj* if possible."""
    results: List[dict] = []
    if isinstance(obj, dict):
        # single dict container
        if "nli_results" in obj and isinstance(obj["nli_results"], list):
            results.extend(obj["nli_results"])
        elif "pairs" in obj and isinstance(obj["pairs"], list):
            results.extend(obj["pairs"])
        elif "premise_raw" in obj and "hypothesis_raw" in obj:
            results.append(obj)  # already a pair‑dict
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_flatten_nli_container(item))
    return results


def _load_pairs(json_file: Path | str) -> List[dict]:
    """Read the JSON produced by the NLI stage and *always* return a **flat** list
    of pair‑dicts, each exposing the keys `premise_raw` and `hypothesis_raw`.
    """
    with open(json_file, "r", encoding="utf-8") as f:
        raw = json.load(f)

    pairs = _flatten_nli_container(raw)
    if not pairs:
        raise ValueError(
            "JSON does not appear to contain NLI results with 'premise_raw' / 'hypothesis_raw'."
        )
    return pairs


def _next_valid_idx(pairs: List[dict], start: int, seen: Set[str]) -> int | None:
    """Return the index of the next pair whose texts are unseen, or *None*."""
    for i in range(start, len(pairs)):
        p = pairs[i]
        if p["premise_raw"] not in seen and p["hypothesis_raw"] not in seen:
            return i
    return None


def _preview_html(span: str) -> str:
    """Wrap span text into a bordered box for nicer display."""
    if not span:
        span = "—"
    escaped = span.replace("\n", "<br>")
    return f"<div style='border:1px solid #888;padding:8px;min-height:160px'>{escaped}</div>"


def _make_temp_file(text: str) -> str:
    tmp = Path(tempfile.mkdtemp()) / "final_text.txt"
    tmp.write_text(text, encoding="utf-8")
    return str(tmp)


# ---------------------------------------------------------------------------
#  Gradio callbacks
# ---------------------------------------------------------------------------


def choose(
    choice: str,  # "left" | "right" | "skip"
    pairs: List[dict],
    idx: int,
    seen: List[str],
    final: List[str],
) -> Tuple[str, str, str, str, int, Set[str], List[str]]:
    """Handle the user choice and advance to the next pair."""
    seen = set(seen or [])
    # If no valid index (finished)
    if idx == -1:
        return "—", "", "", "\n\n".join(final), -1, seen, final

    # Record the selection
    if choice in {"left", "right"}:
        selected = (
            pairs[idx]["premise_raw"]
            if choice == "left"
            else pairs[idx]["hypothesis_raw"]
        )
        final = [*final, selected]
        seen = set(seen) | {pairs[idx]["premise_raw"], pairs[idx]["hypothesis_raw"]}

    # Compute next index
    next_idx = _next_valid_idx(pairs, idx + 1, seen)
    if next_idx is None:
        # No more pairs – finished
        return (
            "✓ Done – no more spans",
            "",
            "",
            " ".join(final),
            -1,
            list(seen),
            final,
        )

    pair = pairs[next_idx]
    lbl = pair.get("label", "—")
    conf = pair.get("confidence")
    label_text = (
        f"Label: {lbl}" if conf is None else f"Label: {lbl} │ Confidence: {conf:.3f}"
    )
    return (
        label_text,
        _preview_html(pair["premise_raw"]),
        _preview_html(pair["hypothesis_raw"]),
        " ".join(final),
        next_idx,
        list(seen),
        final,
    )


def download(final: List[str]) -> str:
    if not final:
        raise gr.Error("Nothing selected yet.")
    return _make_temp_file(" ".join(final))


# ---------------------------------------------------------------------------
#  Gradio UI
# ---------------------------------------------------------------------------

with gr.Blocks() as demo:
    gr.Markdown("## 3. Build final text")

    pairs_state = gr.State([])
    idx_state = gr.State(-1)
    seen_state = gr.State([])
    final_state = gr.State([])

    # 1 · Upload JSON from the NLI stage -------------------------------------
    json_input = gr.File(label="Upload NLI JSON", file_types=[".json"])

    load_btn = gr.Button("Load file and start")

    label_md = gr.Markdown("Label: —", elem_id="label_box")
    with gr.Row():
        left_html = gr.HTML()
        right_html = gr.HTML()
    final_preview = gr.Textbox(label="Final document", lines=6, interactive=False)

    # Choice buttons
    with gr.Row():
        choose_left = gr.Button("← Choose left", variant="primary")
        skip = gr.Button("Skip", variant="secondary")
        choose_right = gr.Button("Choose right →", variant="primary")

    # Hidden slider to keep track of current idx (not displayed)
    idx_slider = gr.Number(value=-1, visible=False, precision=0)

    download_btn = gr.Button("Download final text")
    download_file = gr.File(label=" ")

    # ── Bind callbacks ─────────────────────────────────────────────────────
    def _load(json_file):
        pairs = _load_pairs(json_file.name)
        first_idx = _next_valid_idx(pairs, 0, set())
        if first_idx is None:
            raise gr.Error("Every span is duplicated – nothing to choose.")
        p = pairs[first_idx]
        return (
            pairs,
            first_idx,
            set(),
            [],
            f"Label: {p.get('label', 'None')} │ Confidence: {_fmt_conf(p.get('confidence'))}",
            _preview_html(p["premise_raw"]),
            _preview_html(p["hypothesis_raw"]),
            "",
            first_idx,
        )

    load_btn.click(
        _load,
        inputs=json_input,
        outputs=[
            pairs_state,
            idx_state,
            seen_state,
            final_state,
            label_md,
            left_html,
            right_html,
            final_preview,
            idx_slider,
        ],
    )

    choose_left.click(
        choose,
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
    choose_right.click(
        choose,
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
    skip.click(
        choose,
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

    download_btn.click(
        download,
        inputs=final_state,
        outputs=download_file,
    )
