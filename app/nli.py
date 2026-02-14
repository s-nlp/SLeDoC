import html
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

import gradio as gr

from .settings import BASE_CSS, CUSTOM_JS, SIDEBAR_CSS, nav_tag

EXTRA_CSS = BASE_CSS + SIDEBAR_CSS
PASTELS = ["#dbeafe55", "#ddd6fe55", "#e5e5e555"]  # faint pastels
ENTAIL_CLR, CONTRA_CLR = "#22c55e", "#f43f5e"  # bright colours
DATA_FILE = Path("example_data/nli_viewer_llm.json")  # initial demo data
# Visual colors per label
COLOR_MAP = {
    "entailment": "#D1FADF",  # green-ish
    "contradiction": "#FFE2E2",  # red-ish
    "neutral": "#E6F0FF",  # blue-ish
}


def _escape(s: str) -> str:
    return html.escape(s, quote=False)


def _span_regex(span: str) -> re.Pattern:
    """
    Build a tolerant regex for a given span:
    - collapse any whitespace runs in span to \\s+
    - exact match for other chars (escaped)
    """
    s = span.strip()
    # Escape everything
    s = re.escape(s)
    # Turn escaped spaces + other whitespace into \s+
    s = re.sub(r"(\\\s)+", r"\\s+", s)
    # Be tolerant to optional trailing punctuation whitespace (common with dots)
    # (safe no-op in most cases)
    return re.compile(s, flags=re.DOTALL)


def _find_non_overlapping(text: str, spans: List[str]) -> List[Tuple[int, int, str]]:
    """
    For each span in order, find the next non-overlapping occurrence in `text`.
    Returns list of (start, end, original_span).
    - Uses tolerant regex (whitespace-insensitive).
    - If duplicate span appears multiple times, chooses the first unused window
      after the previous end.
    """
    pos = 0
    hits: List[Tuple[int, int, str]] = []
    for sp in spans:
        if not sp:
            continue
        pat = _span_regex(sp)
        # search starting at current cursor 'pos' to avoid reusing the same occurrence
        m = pat.search(text, pos)
        if m is None:
            # fallback: try from 0 (sometimes order differs slightly)
            m = pat.search(text, 0)
            if m is None:
                # didn't find — skip; we won't crash
                continue
        s, e = m.span()
        hits.append((s, e, sp))
        # move cursor to end of this match (non-overlap)
        pos = e
    # sort by start index, just in case
    hits.sort(key=lambda t: t[0])
    return hits


def _inject_spans(
    text: str,
    matches: List[Tuple[int, int, str]],
    prefix: str,
    link_map: Dict[str, str],
    color_getter,
) -> str:
    """
    Inject <span class="hl"> wrappers into text at given positions.
    - prefix: "p1" or "p2"
    - link_map: maps ids on the left to ids on the right (filled outside)
    - color_getter: callable(span_id) -> color to paint on hover
    Emits ids like f"{prefix}_{i}" and sets data-target if present in link_map.
    """
    out = []
    last = 0
    for i, (s, e, _sp) in enumerate(matches):
        span_id = f"{prefix}_{i}"
        out.append(_escape(text[last:s]))
        tgt = link_map.get(span_id, "")
        # each span knows which target to light up; also store preferred color
        hcolor = color_getter(span_id)
        segment = text[s:e]
        out.append(
            f'<span id="{span_id}" class="hl" '
            f'data-target="{_escape(tgt)}" '
            f'data-hcolor="{_escape(hcolor)}" '
            f'data-claim="{_escape(segment)}" '
            f'data-conf="">'
            f"{_escape(segment)}"
            f"</span>"
        )
        last = e
    out.append(_escape(text[last:]))
    return "".join(out)


def render_nli_item(item: dict) -> Tuple[str, str]:
    """
    Returns HTML for left and right texts with injected <span> that are linked.
    Expects 'input_1', 'input_2', 'output_1', 'output_2', 'nli_results'.
    """
    left = str(item.get("input_1", "") or "")
    right = str(item.get("input_2", "") or "")

    # Collect spans from nli_results in order, using premise_raw/hypothesis_raw
    pairs: List[Tuple[str, str, str]] = []
    for r in item.get("nli_results", []) or []:
        s1 = str(r.get("premise_raw", r.get("premise", "")) or "").strip()
        s2 = str(r.get("hypothesis_raw", r.get("hypothesis", "")) or "").strip()
        lab = (r.get("label") or "neutral").lower()
        pairs.append((s1, s2, lab))

    # Find where each left/right span occurs (non-overlapping and stable)
    left_spans = [p[0] for p in pairs if p[0]]
    right_spans = [p[1] for p in pairs if p[1]]

    left_hits = _find_non_overlapping(left, left_spans)  # [(s,e,span)]
    right_hits = _find_non_overlapping(right, right_spans)  # [(s,e,span)]

    # Build index of the positions by text to be able to link by content
    # Note: we map by order of pairs; for duplicates, we advance pointers.
    # Pointers ensure one-to-one alignment in the original nli_results order.
    def _index_map(hits: List[Tuple[int, int, str]]) -> Dict[str, List[int]]:
        d: Dict[str, List[int]] = {}
        for idx, (_s, _e, sp) in enumerate(hits):
            d.setdefault(sp, []).append(idx)
        return d

    left_pool = _index_map(left_hits)
    right_pool = _index_map(right_hits)

    # link_map: p1_<i> -> p2_<j> (and reverse) + color map per edge
    link_map_l2r: Dict[str, str] = {}
    link_map_r2l: Dict[str, str] = {}
    edge_color: Dict[Tuple[str, str], str] = {}

    # We also need label per connection to color both ends consistently
    for s1, s2, lab in pairs:
        if not s1 or not s2:
            continue
        lst = left_pool.get(s1, [])
        rst = right_pool.get(s2, [])
        if not lst or not rst:
            # nothing to link for this pair
            continue
        li = lst.pop(0)
        ri = rst.pop(0)
        # update back the pools
        left_pool[s1] = lst
        right_pool[s2] = rst

        lid = f"p1_{li}"
        rid = f"p2_{ri}"
        link_map_l2r[lid] = rid
        link_map_r2l[rid] = lid

        color = COLOR_MAP.get(lab, COLOR_MAP["neutral"])
        edge_color[("L", lid)] = color
        edge_color[("R", rid)] = color

    def _color_getter_left(span_id: str) -> str:
        return edge_color.get(("L", span_id), COLOR_MAP["neutral"])

    def _color_getter_right(span_id: str) -> str:
        return edge_color.get(("R", span_id), COLOR_MAP["neutral"])

    # Inject <span> wrappers
    left_html = _inject_spans(
        left,
        [(s, e, sp) for i, (s, e, sp) in enumerate(left_hits)],
        "p1",
        link_map_l2r,
        _color_getter_left,
    )
    right_html = _inject_spans(
        right,
        [(s, e, sp) for i, (s, e, sp) in enumerate(right_hits)],
        "p2",
        link_map_r2l,
        _color_getter_right,
    )

    return left_html, right_html


def load_pairs(path_or_handle):
    if isinstance(path_or_handle, (str, Path)):
        text = Path(path_or_handle).read_text(encoding="utf-8")
    else:
        text = path_or_handle.read().decode()
    return (
        json.loads(text)
        if text.lstrip()[0] == "["
        else [json.loads(l_) for l_ in text.splitlines() if l_.strip()]
    )


pairs = load_pairs(DATA_FILE)


def make_partner_map(item):
    """
    Build a lookup: span-id → {'target': partner-id, 'color': #hex, 'conf': float}
    """
    idx1 = {d["input"]: i for i, d in enumerate(item["output_1"])}
    idx2 = {d["input"]: i for i, d in enumerate(item["output_2"])}
    mp = {}
    for r in item["nli_results"]:
        if r["label"] not in ("entailment", "contradiction"):
            continue
        col = ENTAIL_CLR if r["label"] == "entailment" else CONTRA_CLR

        # case 1: premise in paragraph-1, hypothesis in paragraph-2
        if r["premise"] in idx1 and r["hypothesis"] in idx2:
            i, j = idx1[r["premise"]], idx2[r["hypothesis"]]

        # case 2: premise in paragraph-2, hypothesis in paragraph-1
        # elif r["premise"] in idx2 and r["hypothesis"] in idx1:
        #     j, i = idx1[r["hypothesis"]], idx2[r["premise"]]
        elif r["premise"] in idx2 and r["hypothesis"] in idx1:
            i, j = idx1[r["hypothesis"]], idx2[r["premise"]]

        else:
            continue
        mp[f"p1_{i}"] = {"target": f"p2_{j}", "color": col, "conf": r["confidence"]}
        mp[f"p2_{j}"] = {"target": f"p1_{i}", "color": col, "conf": r["confidence"]}
    return mp


def highlight(text, snippets, tag_prefix, pmap):
    safe = html.escape(text)
    for i, s in enumerate(
        sorted(snippets, key=lambda x: len(x["input"]), reverse=True)
    ):
        sid = f"{tag_prefix}_{i}"
        base = PASTELS[i % len(PASTELS)]
        info = pmap.get(sid, {})
        span = (
            f'<span class="hl" id="{sid}" '
            f'data-claim="{html.escape(s.get("claim",""),quote=True)}" '
            f'data-target="{info.get("target","")}" '
            f'data-hcolor="{info.get("color","")}" '
            f'data-conf="{info.get("conf","")}" '
            f'style="background-color:{base};">'
            f'{html.escape(s["input"])}</span>'
        )
        safe = re.sub(re.escape(html.escape(s["input"])), span, safe, count=1)
    return f'<div style="font-size:14px;line-height:1.4;">{safe}</div>'


def render(idx):
    item = pairs[idx]
    para1, para2 = render_nli_item(item)
    return para1, para2


# ─────────── UI layout ------------------------------------------------------
with gr.Blocks(css=EXTRA_CSS, js=CUSTOM_JS) as demo:
    gr.Markdown("## NLI viewer")
    # ─ sidebar nav
    gr.HTML(nav_tag, visible=True)

    # ─── file loader row ───────────────────────────────────────────────────
    with gr.Row():
        file_in = gr.File(
            label="Upload JSON(.json/.jsonl)",
            file_types=[".json", ".jsonl"],
            file_count="single",
        )
        load_btn = gr.Button("Load")

    # ─── navigation row: ◀ slider ▶ + confidence display ──────────────────
    with gr.Row():
        prev_btn = gr.Button("◀ Prev")
        idx = gr.Slider(
            minimum=0,
            maximum=len(pairs) - 1,
            value=0,
            step=1,
            show_label=False,
            container=False,
        )
        next_btn = gr.Button("Next ▶")
        conf_box = gr.HTML(
            '<div id="conf_box"><b>Confidence:</b> -</div>', elem_id="conf_box"
        )

    # ─── two paragraph panes ───────────────────────────────────────────────
    with gr.Row():
        para1 = gr.HTML(elem_classes="para-box")
        para2 = gr.HTML(elem_classes="para-box")

    # ─── callbacks (only Python → HTML; all interactivity in JS) ───────────
    idx.change(lambda i: render(i), inputs=idx, outputs=[para1, para2])

    def move(i, d):  # d = -1 for prev, +1 for next
        new = max(0, min(len(pairs) - 1, i + d))
        return (*render(new), gr.update(value=new))

    prev_btn.click(lambda i: move(i, -1), inputs=idx, outputs=[para1, para2, idx])
    next_btn.click(lambda i: move(i, +1), inputs=idx, outputs=[para1, para2, idx])

    def load(file):
        global pairs
        pairs = load_pairs(file)
        return (*render(0), gr.update(value=0, minimum=0, maximum=len(pairs) - 1))

    load_btn.click(load, inputs=file_in, outputs=[para1, para2, idx])

    demo.load(lambda: render(0), None, [para1, para2])

if __name__ == "__main__":
    demo.launch()
