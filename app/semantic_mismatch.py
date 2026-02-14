import html
import json
from pathlib import Path

import gradio as gr

from .settings import SIDEBAR_CSS, nav_tag

EXTRA_CSS = """
.para-box{
    border:1px solid #000;
    padding:8px;
    min-height:320px;
    min-width:320px
    /* overflow: visible; */    /* <— allow the tooltip to extend outside */
}

/* ───────── coloured-span tooltip */
.hl{
    position:relative;
    cursor:help;
}
.hl.selected     { background-color:#ffff66 !important; outline:2px solid #000; }
.hl.dimmed       { opacity:.35; }
.hl:hover::after,
.hl:focus::after{                       /* include :focus if you kept that */
    content:attr(data-claim);
    position:absolute;
    left:0;                             /* tweak if you want it centred */
    top:100%;                           /* shows just below the text    */
    /* ── SIZE ──────────────────────── */
    /* width: max-content; */
    max-width: 1000px;
    min-width: 240px;
    white-space: pre-wrap;              /* for \n to not break */  /* white-space: normal;   wraps text inside the box */
    /* ── cosmetics ─────── */
    z-index:10;
    background:#333;
    color:#fff;
    padding:6px 8px;
    border-radius:4px;
    font-size:13px;
    line-height:1.3;
    box-shadow:0 2px 6px rgba(0,0,0,.25);
}
/* visual states controlled by JS  */
.hl.selected{background-color:#ffff66 !important; outline:2px solid #000;}
.hl.dimmed  {opacity:.35;}
"""

EXTRA_CSS += SIDEBAR_CSS


DEFAULT_JSON = Path("example_data/pairs.json")
COLOR_PALETTE = [
    # "#d1e7dd",  # light green
    "#dbeafe55",  # light blue
    # "#fde68a",  # light yellow
    # "#fecaca",  # light red
    "#ddd6fe55",  # light violet
    # "#fecdd3",  # light pink
    "#e5e5e555",  # grey
]


# ---------- helpers ---------------------------------------------------------
def load_pairs(path_or_handle):
    """Accept Path *or* an uploaded file handle and return list-of-dicts."""
    if isinstance(path_or_handle, (str, Path)):
        with open(path_or_handle, encoding="utf-8") as f:
            return json.load(f)
    # gr.File sends a tempfile.NamedTemporaryFile – read from .name
    with open(path_or_handle.name, encoding="utf-8") as f:
        return json.load(f)


pairs = load_pairs(DEFAULT_JSON)  # initial content


def _highlight(text: str, snippets: list[dict]) -> str:
    safe = html.escape(text)
    for i, s in enumerate(
        sorted(snippets, key=lambda x: len(x["input"]), reverse=True)
    ):
        colour = COLOR_PALETTE[i % len(COLOR_PALETTE)]
        piece = html.escape(s["input"])
        claim = html.escape(s.get("claim", ""), quote=True)
        safe = safe.replace(
            piece,
            # reinstated class + data-claim -----------------------------▼▼▼
            f"<span class='hl' data-claim=\"{claim}\" "
            f"style='background-color:{colour};'>{piece}</span>",
            1,  # replace the first occurrence only – optional
        )
    return f"<div style='font-size:14px;line-height:1.4;'>{safe}</div>"


def render(index: int):
    item = pairs[index]
    sim = round(item["similarity"], 3)
    simbox = f"<div id='sim_box'><b>Cosine&nbsp;similarity:</b> {sim}</div>"
    return (
        _highlight(item["paragraph_1"], item["output_1"]),
        _highlight(item["paragraph_2"], item["output_2"]),
        simbox,
    )


# ---------- callback for *Load* button -------------------------------------
def load_json(uploaded_file):
    """
    Replace the global `pairs` with the newly uploaded list and show pair 0.
    Returns updates for: para-1, para-2, similarity-box, slider.
    """
    global pairs
    try:
        pairs = load_pairs(uploaded_file)
        if not isinstance(pairs, list) or len(pairs) == 0:
            raise ValueError("Empty / wrong-format JSON")
    except Exception as e:
        # simple error surface – you can get fancier, of course
        err_html = f"<div style='color:red;'>❌ {html.escape(str(e))}</div>"
        return err_html, err_html, 0, gr.update()

    p1, p2, sim = render(0)
    slider_cfg = gr.update(value=0, minimum=0, maximum=len(pairs) - 1)
    return p1, p2, sim, slider_cfg


CUSTOM_JS = """
() => {
  /* remove every highlight state */
  const clear = () => document
        .querySelectorAll('span.hl.selected, span.hl.dimmed')
        .forEach(el => el.classList.remove('selected','dimmed'));

  document.addEventListener('click', ev => {
      const span = ev.target.closest('span.hl');

      /* always begin by clearing the old state */
      clear();

      /* clicked a highlight?  select + dim the rest */
      if(span){
          span.classList.add('selected');
          document
            .querySelectorAll('span.hl:not(.selected)')
            .forEach(el => el.classList.add('dimmed'));
      }
  });
}
"""

# UI
with gr.Blocks(css=EXTRA_CSS, js=CUSTOM_JS) as demo:
    gr.Markdown("## Semantic Mismatch Viewer")
    # ─ sidebar nav
    gr.HTML(nav_tag, visible=True)

    # ─── upload row ──────────────────────────────────────────────────────────
    with gr.Row():
        file_input = gr.File(
            label="Upload JSON (.json)", file_types=[".json"], file_count="single"
        )
        load_btn = gr.Button("Load")

    # ─── slider + similarity ────────────────────────────────────────────────
    with gr.Row():
        prev_btn = gr.Button("◀ Prev")
        idx_slider = gr.Slider(
            minimum=0,
            maximum=len(pairs) - 1,
            value=0,
            step=1,
            show_label=False,
            container=False,
        )
        next_btn = gr.Button("Next ▶")
        sim_box = gr.HTML(elem_id="sim_box")  # populated by render

    # ─── two paragraph panes ────────────────────────────────────────────────
    with gr.Row():
        para1_html = gr.HTML(elem_classes="para-box")
        para2_html = gr.HTML(elem_classes="para-box")

    # ─── events ─────────────────────────────────────────────────────────────
    idx_slider.change(
        fn=render, inputs=idx_slider, outputs=[para1_html, para2_html, sim_box]
    )

    def move(i, delta):
        new = max(0, min(len(pairs) - 1, i + delta))
        return (*render(new), gr.update(value=new))

    prev_btn.click(
        lambda i: move(i, -1),
        inputs=idx_slider,
        outputs=[para1_html, para2_html, sim_box, idx_slider],
    )
    next_btn.click(
        lambda i: move(i, +1),
        inputs=idx_slider,
        outputs=[para1_html, para2_html, sim_box, idx_slider],
    )

    load_btn.click(
        fn=load_json,
        inputs=file_input,
        outputs=[para1_html, para2_html, sim_box, idx_slider],
    )

    # initial paint
    demo.load(lambda: (*render(0),), None, [para1_html, para2_html, sim_box])

if __name__ == "__main__":
    demo.launch()
