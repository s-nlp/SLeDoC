import html
import json
import re
from pathlib import Path

import gradio as gr

from .settings import nav_tag, side_bar

EXTRA_CSS = """
.para-box{
    border:1px solid #000; padding:8px; min-height:320px; min-width:320px;
}
.hl{position:relative; cursor:help;}
.hl.selected     { background-color:#ffff66 !important; outline:2px solid #000; }
.hl.dimmed       { opacity:.35; }
.hl:hover::after,.hl:focus::after{
    content:attr(data-claim);
    position:absolute; left:0; top:100%;
    max-width:1000px; min-width:240px; white-space:pre-wrap;
    z-index:10; background:#333; color:#fff; padding:6px 8px; border-radius:4px;
    font-size:13px; line-height:1.3; box-shadow:0 2px 6px rgba(0,0,0,.25);
}
"""

EXTRA_CSS += side_bar


PASTELS = ["#dbeafe55", "#ddd6fe55", "#e5e5e555"]  # faint pastels
ENTAIL_CLR, CONTRA_CLR = "#22c55e", "#f43f5e"  # bright colours
DATA_FILE = Path("example_data/nli_test.jsonl")  # initial demo data


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
    pmap = make_partner_map(item)
    para1 = highlight(item["input_1"], item["output_1"], "p1", pmap)
    para2 = highlight(item["input_2"], item["output_2"], "p2", pmap)
    return para1, para2


CUSTOM_JS = """
() => {
  const confBox = () => document.getElementById('conf_box');
  const hi   = (id,col) => { const e=document.getElementById(id);
      if(!e)return; e.dataset._bg=e.style.backgroundColor;
      e.style.backgroundColor=col; e.style.outline='2px solid #000'; };
  const bye  = id => { const e=document.getElementById(id);
      if(!e||!e.dataset._bg)return;
      e.style.backgroundColor=e.dataset._bg; e.style.outline=''; };

  document.addEventListener('mouseover', ev=>{
      const s=ev.target.closest('span.hl');
      if(s && s.dataset.target){
          hi(s.dataset.target, s.dataset.hcolor);
          const c=parseFloat(s.dataset.conf||'');
          confBox().textContent = 'Confidence: ' + (isNaN(c)?'-':c.toFixed(3));
      }
  });
  document.addEventListener('mouseout', ev=>{
      const s=ev.target.closest('span.hl');
      if(s && s.dataset.target){
          bye(s.dataset.target);
          confBox().textContent = 'Confidence: -';
      }
  });
  /* click = lock / unlock */
    document.addEventListener('click', ev=>{
    const span = ev.target.closest('span.hl');
    if(!span) return;

    /* Clear previous selection */
    document.querySelectorAll('span.hl.selected, span.hl.dimmed')
            .forEach(el => { el.classList.remove('selected','dimmed'); });

    /* Select the clicked span and its counterpart (if any) */
    const targetId = span.dataset.target;
    span.classList.add('selected');
    if(targetId){
        const mate = document.getElementById(targetId);
        if(mate) mate.classList.add('selected');
    }

    /* Dim every other span to emphasise the pair */
    document.querySelectorAll('span.hl:not(.selected)')
            .forEach(el => el.classList.add('dimmed'));
    });
}
"""

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
