from __future__ import annotations

import asyncio
import difflib
import hashlib
import html
import json
import re
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
from app.openai_client import make_client

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
.right-pane { flex: 1 1 0; position: static; max-height: 80vh; overflow:auto; }

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
.hl.contradiction  { background: rgba(244,63,94,.18); }
/* contradiction term highlight */
.contra-term{ background: #fff59a; padding:0 2px; border-radius:3px; }
   /* red */

/* selected state: strong outline, keep original background color */
.hl.selected { outline:2px solid #000 !important; }

/* mute tooltip artifacts */
.hl::after { display:none !important; }

/* right mirror */
.mirror-box{
  border:1px solid #adb5bd; padding:12px; border-radius:12px; background:#fafafa;
  min-height:140px;
}

.anch{ font-size:11px; opacity:.8; margin-left:4px; text-decoration:none; }

/* legend + confidence UI */
.toolbar { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin:8px 0; }
.legend { display:flex; gap:12px; align-items:center; font-size:12px; color:#475569; }
.legend .key { display:inline-flex; align-items:center; gap:6px; }
.legend .dot { width:10px; height:10px; border-radius:2px; display:inline-block; }
.legend .dot.ent { background:#22c55e; } /* entailment */
.legend .dot.con { background:#f43f5e; } /* contradiction */
.legend .dot.neu { background:#3b82f6; } /* addition/neutral */
#conf_box { font-weight:600; }

/* dynamic heights */
.para-box{ min-height: unset; }
.mirror-box{ min-height: unset; }

/* right pane: flows with page scroll (no inner scroll, no sticky) */
#right_pane{ position: static; }

/* reasoning panel */
.reason-wrap{ margin-top:8px; display:flex; flex-direction:column; gap:8px; }
.reason-card{ border:1px dashed #cbd5e1; background:#fff; padding:8px 10px; border-radius:10px; font-size:14px; }

.contra-box{margin-top:10px;padding:10px;border:1px solid #e5e7eb;border-radius:10px;background:#fafafa}
.contra-head{font-weight:600;margin-bottom:6px}
.contra-row{display:flex;gap:8px;align-items:flex-start;margin:4px 0}
.side-tag{font-size:12px;color:#6b7280;padding:2px 6px;border:1px solid #e5e7eb;border-radius:9999px}
.side-pills{display:flex;gap:6px;flex-wrap:wrap}
.pill{display:inline-block;padding:2px 8px;border:1px solid #d1d5db;border-radius:9999px;background:white;font-size:12px}
.contra-src{margin-top:8px;font-size:12px;color:#6b7280;display:grid;gap:2px}
.src-tag{font-weight:600;color:#4b5563}
"""
)


# ----------------------------- Helpers -----------------------------
def _escape(s: str) -> str:
    return html.escape(s or "", quote=False).replace("\n", "<br>")


RUS_STOPWORDS_SHORT = {
    "на",
    "о",
    "по",
    "об",
    "от",
    "до",
    "из",
    "за",
    "у",

}
MIN_TERM_ALNUM_LEN = 2  # require ≥2 alnum chars to highlight


def _alnum_len(s: str) -> int:
    # count letters/digits/underscore in Unicode
    return len(re.sub(r"[^\w]", "", s, flags=re.UNICODE))


def _wrap_terms_html(text: str, terms: List[str]) -> str:
    """
    HTML-escape text and wrap selected terms/phrases in <mark class="contra-term">…</mark>.
    - Ignores very short items and common 1–2 char function words.
    - Matches only on token boundaries (no mid-word matches).
    - Case-insensitive. Longer phrases take precedence.
    """
    if not text:
        return ""
    if not terms:
        return _escape(text)

    # normalize, de-dup, length filter, stopword filter
    cleaned = []
    seen = set()
    for t in sorted((t or "").strip() for t in terms if t):
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        if key in RUS_STOPWORDS_SHORT:
            continue
        if _alnum_len(t) < MIN_TERM_ALNUM_LEN:
            continue
        cleaned.append(t)

    if not cleaned:
        return _escape(text)

    # Build boundary-safe alternation:
    # (?<!\w)term(?!\w) ensures we highlight whole tokens/phrases only.
    parts = [
        rf"(?<!\w){re.escape(t)}(?!\w)" for t in sorted(cleaned, key=len, reverse=True)
    ]
    pattern = "(?:" + "|".join(parts) + ")"

    try:
        rx = re.compile(pattern, flags=re.IGNORECASE | re.UNICODE)
    except Exception:
        # On any regex build issue, just return escaped text
        return _escape(text)

    out, last = [], 0
    for m in rx.finditer(text):
        out.append(_escape(text[last : m.start()]))
        out.append(f'<mark class="contra-term">{_escape(m.group(0))}</mark>')
        last = m.end()
    out.append(_escape(text[last:]))
    return "".join(out)


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


# cache to avoid repeat calls for same (left,right)
_CONTRA_CACHE: Dict[str, Dict[str, List[str]]] = {}


def _hash_pair(a: str, b: str) -> str:
    return hashlib.sha1((a + "␞" + b).encode("utf-8")).hexdigest()


def _fallback_contra_terms(left: str, right: str) -> Dict[str, List[str]]:
    # token diff fallback (deterministic, fast)
    WORD = re.compile(
        r"[A-Za-zА-Яа-яЁёІіЇїҐґ0-9]+|[^\sA-Za-zА-Яа-яЁёІіЇїҐґ0-9]", re.UNICODE
    )
    lt = WORD.findall(left or "")
    rt = WORD.findall(right or "")
    sm = difflib.SequenceMatcher(a=lt, b=rt)
    bad_l, bad_r = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            bad_l += [t for t in lt[i1:i2] if re.search(r"\w", t)]
            bad_r += [t for t in rt[j1:j2] if re.search(r"\w", t)]

    # keep unique while preserving order
    def uniq(xs):
        seen = set()
        out = []
        for x in xs:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    return {"from_span_1": uniq(bad_l), "from_span_2": uniq(bad_r)}


async def _llm_contra_terms_async(
    left: str, right: str, model_id: str
) -> Dict[str, List[str]]:
    """
    Ask LLM for the exact contradicting words/short phrases.
    Returns {"from_span_1":[...], "from_span_2":[...]}.
    Falls back to token diff on error.
    """
    try:
        client, mid = make_client(model_id)
        prompt = (
            "Here are two spans of Russian text that contradict each other.\n"
            "Your task: extract SHORT words/phrases (1–4 words) that constitute the contradiction.\n"
            "Return JSON ONLY in this form:\n"
            '{"from_span_1": ["..."], "from_span_2": ["..."]}\n'
            "Do not add any commentary.\n\n"
            f"span_1: {left}\n"
            f"span_2: {right}\n"
        )
        resp = await client.chat.completions.create(
            model=mid,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        # basic hygiene
        a = [str(x).strip() for x in data.get("from_span_1", []) if str(x).strip()]
        b = [str(x).strip() for x in data.get("from_span_2", []) if str(x).strip()]
        if not a and not b:
            raise ValueError("empty LLM result")
        return {"from_span_1": a, "from_span_2": b}
    except Exception:
        return _fallback_contra_terms(left, right)


def _get_contra_terms(
    left: str, right: str, use_llm: bool, model_id: str
) -> Dict[str, List[str]]:
    key = _hash_pair(left, right) + ("#llm" if use_llm else "#diff")
    if key in _CONTRA_CACHE:
        return _CONTRA_CACHE[key]
    if use_llm:
        # run sync-friendly
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            result = loop.run_until_complete(_llm_contra_terms_async(left, right, model_id))  # type: ignore
        else:
            result = asyncio.run(_llm_contra_terms_async(left, right, model_id))
    else:
        result = _fallback_contra_terms(left, right)
    _CONTRA_CACHE[key] = result
    return result


def _compute_contra_terms_for_focus(
    pairs: List[Dict[str, Any]],
    focus: Tuple[int, Optional[int]],
    use_llm: bool,
    model_id: str,
):
    """Return (terms_dict, right_idx) or (None, None) if not available."""
    if not pairs:
        return None, None
    k, i_left = focus
    if i_left is None or k is None or k >= len(pairs):
        return None, None
    b = pairs[k]
    out1 = b.get("output_1") or []
    out2 = b.get("output_2") or []
    if not (0 <= i_left < len(out1)):
        return None, None
    links, _ = _link_map_for_pair(b)
    cands = [
        (rj, lbl)
        for (rj, lbl) in links.get(i_left, [])
        if str(lbl).lower() == "contradiction"
    ]
    if not cands:
        return None, None
    rj, _ = cands[0]
    left = str(out1[i_left].get("claim") or out1[i_left].get("input") or "")
    right = str(out2[rj].get("claim") or out2[rj].get("input") or "")
    terms = _get_contra_terms(
        left, right, use_llm=use_llm, model_id=model_id or "gpt-4o-mini"
    )
    return {"terms": terms, "right_idx": rj}


def _render_contra_box_html(terms: Dict[str, List[str]], left: str, right: str) -> str:
    def pills(items: List[str]) -> str:
        if not items:
            return '<span class="pill">—</span>'
        return " ".join(f'<span class="pill">{_escape(x)}</span>' for x in items)

    return (
        '<div class="contra-box">'
        '<div class="contra-head">🔎 Contradiction focus</div>'
        '<div class="contra-row"><div class="side-tag">span_1</div>'
        f'<div class="side-pills">{pills(terms.get("from_span_1", []))}</div></div>'
        '<div class="contra-row"><div class="side-tag">span_2</div>'
        f'<div class="side-pills">{pills(terms.get("from_span_2", []))}</div></div>'
        '<div class="contra-src">'
        f'<div><span class="src-tag">span_1:</span> {_escape(left)}</div>'
        f'<div><span class="src-tag">span_2:</span> {_escape(right)}</div>'
        "</div>"
        "</div>"
    )


_EMPTY_CONTRA = '<div class="contra-box"><em>Select a span to analyze.</em></div>'


def _render_contradiction_box(
    pairs: list, focus: tuple, use_llm: bool, model_id: str
) -> str:
    # focus is (pair_idx, i_left) in your current bridge
    if not pairs:
        return '<div class="contra-box"><em>Load a pair to analyze.</em></div>'
    k, i_left = focus
    if i_left is None or k is None or k >= len(pairs):
        return '<div class="contra-box"><em>Select a span to analyze.</em></div>'

    b = pairs[k]
    out1 = b.get("output_1") or []
    out2 = b.get("output_2") or []
    if not (0 <= i_left < len(out1)):
        return '<div class="contra-box"><em>Select a span to analyze.</em></div>'

    links, _ = _link_map_for_pair(b)
    cands = [
        (rj, lbl)
        for (rj, lbl) in links.get(i_left, [])
        if str(lbl).lower() == "contradiction"
    ]
    if not cands:
        return '<div class="contra-box"><em>No contradiction for this span.</em></div>'

    rj, _ = cands[0]
    left = str(out1[i_left].get("claim") or out1[i_left].get("input") or "")
    right = str(out2[rj].get("claim") or out2[rj].get("input") or "")

    terms = _get_contra_terms(
        left, right, use_llm=use_llm, model_id=model_id or "gpt-4o-mini"
    )
    return _render_contra_box_html(terms, left, right)


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


def _legend_html() -> str:
    return (
        '<div class="toolbar">'
        '<div id="conf_box">Confidence: —</div>'
        '<div class="legend">'
        '<span class="key"><span class="dot ent"></span> entailment (equivalent)</span>'
        '<span class="key"><span class="dot con"></span> contradiction</span>'
        '<span class="key"><span class="dot neu"></span> addition (neutral)</span>'
        "</div>"
        "</div>"
    )


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

  // Use event delegation so listeners survive HTML re-renders
  document.addEventListener('click', function(e){
    // Claim span click
    const span = e.target.closest('.hl');
    if (span) {
      e.stopPropagation();
      // local selection visuals
      document.querySelectorAll('.hl.selected').forEach(el=>el.classList.remove('selected'));
      span.classList.add('selected');
      const pidx = span.getAttribute('data-pair');
      const lidx = span.getAttribute('data-left');
      if (pidx !== null && lidx !== null) emitBridge('S:'+pidx+':'+lidx);
      return;
    }
    // Paragraph card click
    const box = e.target.closest('.para-box');
    if (box && box.hasAttribute('data-idx')) {
      const idx = box.getAttribute('data-idx');
      emitBridge('P:'+idx);
    }
  }, true);
})();
</script>
"""


def _render_left(
    blocks: List[Dict[str, Any]],
    focus: Optional[Tuple[int, Optional[int]]] = None,
    contra_terms: Optional[Dict[str, List[str]]] = None,
) -> str:
    """
    Big left pane: for each pair, show Document A claims as spans, colored by worst NLI link.
    If no claims available for a block, fall back to raw paragraph text.
    """
    html_parts = ['<div class="viewer-wrap"><div class="left-pane">', _legend_html()]
    for pi, b in enumerate(blocks):
        out1 = b.get("output_1") or []
        links, left_color = _link_map_for_pair(b)

        if out1:
            spans = []
            for i1, c in enumerate(out1):
                raw = str(c.get("claim") or c.get("input") or "")
                if focus and focus[0] == pi and focus[1] == i1 and contra_terms:
                    txt = _wrap_terms_html(raw, contra_terms.get("from_span_1") or [])
                else:
                    txt = _escape(raw)
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
    html_parts.append("</div>")  # viewer-wrap
    return "\n".join(html_parts)


def _render_right(
    blocks: List[Dict[str, Any]],
    focus: Tuple[int, Optional[int]],
    contra_terms: Optional[Dict[str, List[str]]] = None,
    target_right_idx: Optional[int] = None,
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
        # worst label for each right claim across all left links
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

    # collect anchors for addition/neutral right spans
    anchor_for_right: Dict[int, str] = {}
    for rr in b.get("nli_results") or []:
        lblr = str(rr.get("label") or "").lower()
        if lblr in ("neutral", "addition"):
            hyp = str(rr.get("hypothesis_raw") or rr.get("hypothesis") or "")
            anc = rr.get("anchor")
            if not anc:
                continue
            for jj, cc in enumerate(out2):
                txtj = cc.get("claim") or cc.get("input") or ""
                if txtj == hyp and jj not in anchor_for_right:
                    anchor_for_right[jj] = str(anc)
                    break
    # build HTML
    if show_indices:
        spans = []
        for j in show_indices:
            c = out2[j]
            raw = str(c.get("claim") or c.get("input") or "")
            if (
                i_left is not None
                and target_right_idx is not None
                and j == target_right_idx
                and (contra_terms or {}).get("from_span_2")
            ):
                txt = _wrap_terms_html(
                    raw, (contra_terms or {}).get("from_span_2") or []
                )
            else:
                txt = _escape(raw)
            cls = "hl " + (label_for_right.get(j, "") or "")
            # add anchor icon + tooltip for addition/neutral
            anchor_sup = ""
            if j in anchor_for_right:
                anchor_sup = f' <sup class="anch" title="anchor: {_escape(anchor_for_right[j])}">🔗</sup>'
            spans.append(
                f'<span id="add-R-{k}-{j}" class="{cls}" data-pair="{k}" data-right="{j}">{txt}</span>{anchor_sup}'
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


REASON_BY_LABEL = {
    "equivalent": "спаны идентичны",
    "entailment": "спаны идентичны",
    "contradiction": "противоречие между утверждениями",
    "addition": "дополнение / новая информация",
    "neutral": "дополнение / новая информация",
}


def _render_reason(blocks, focus):
    k, i_left = focus
    if not blocks or k < 0 or k >= len(blocks) or i_left is None:
        return '<div class="reason-wrap"></div>'
    b = blocks[k]
    out1 = b.get("output_1") or []
    if not (0 <= i_left < len(out1)):
        return '<div class="reason-wrap"></div>'
    left_span = (out1[i_left].get("claim") or out1[i_left].get("input") or "").strip()

    items = []
    for r in b.get("nli_results") or []:
        prem = str(r.get("premise_raw") or r.get("premise") or "")
        hyp = str(r.get("hypothesis_raw") or r.get("hypothesis") or "")
        lab = str(r.get("label") or "").lower()
        if prem == left_span or hyp == left_span:
            reason = (
                r.get("explanation")
                or r.get("reason")
                or r.get("reasoning")
                or REASON_BY_LABEL.get(lab, "")
            )
            if reason:
                items.append(
                    f'<div class="reason-card">{html.escape(str(reason))}</div>'
                )

    if not items:
        # fallback: worst label among links of this left span
        links, _ = _link_map_for_pair(b)
        sev = {"contradiction": 3, "neutral": 2, "entailment": 1}
        worst = None
        for _rj, lbl in links.get(i_left, []):
            if sev.get(lbl, 0) > sev.get(worst or "", 0):
                worst = lbl
        reason = REASON_BY_LABEL.get(worst or "neutral", "")
        if reason:
            items = [f'<div class="reason-card">{html.escape(str(reason))}</div>']

    return '<div class="reason-wrap">' + "".join(items) + "</div>"


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

    # Enforce document length restriction (≤ 5000 characters each)
    try:
        paragraphs_a = merge_incomplete_sentences(get_paragraphs_from_docx(p1))
        paragraphs_b = filter_non_russian(
            separate_points(merge_incomplete_sentences(get_paragraphs_from_docx(p2)))
        )
        len_a = sum(len(x) for x in paragraphs_a)
        len_b = sum(len(x) for x in paragraphs_b)
        if len_a > 5000 or len_b > 5000:
            gr.Warning(
                f"Document too long: A={len_a} chars, B={len_b} chars. "
                f"Limit is 5000. Processing stopped."
            )
            raise RuntimeError("Document length exceeds 5000 characters.")
    except Exception:
        pass

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
            str(claims_path),
        )
        pairs_path = nli_out_path
        pairs = json.loads(Path(pairs_path).read_text(encoding="utf-8"))

    left_html = _render_left(pairs)
    right_html = _render_right(pairs, (0, None))

    return align_path, pairs_path, _preview, left_html, right_html, pairs


def _on_pick(pairs, choice):
    if not pairs:
        return (
            _render_left(
                [],
            ),
            _render_right([], (0, None)),
            _render_reason([], (0, None)),
        )
    try:
        idx = max(0, int(str(choice)) - 1) if choice else 0
    except Exception:
        idx = 0
    return (
        _render_left(pairs),
        _render_right(pairs, (idx, None)),
        _render_reason(pairs, (idx, None)),
    )


def _bridge_update(pairs: List[Dict[str, Any]], bridge_value: str):
    """Lightweight update (no LLM/diff). Just sync selection and clear highlights."""
    try:
        if not bridge_value:
            k = 0
            return (
                _render_left(pairs),
                _render_right(pairs, (0, None)),
                _render_reason(pairs, (0, None)),
                gr.update(value="1"),
            )
        if bridge_value.startswith("P:"):
            k = int(bridge_value.split(":", 1)[1])
            return (
                _render_left(pairs),
                _render_right(pairs, (k, None)),
                _render_reason(pairs, (k, None)),
                gr.update(value=str(k + 1)),
            )
        if bridge_value.startswith("S:"):
            _t, a, b = bridge_value.split(":")
            k, i_left = int(a), int(b)
            return (
                _render_left(pairs),
                _render_right(pairs, (k, i_left)),
                _render_reason(pairs, (k, i_left)),
                gr.update(value=str(k + 1)),
            )
    except Exception:
        pass
    return (
        _render_left(pairs),
        _render_right(pairs, (0, None)),
        _render_reason(pairs, (0, None)),
        gr.update(value="1"),
    )


def _bridge_combo(ps, v, use_llm_contra=False, contra_model_id="gpt-4o-mini"):
    k, l = 0, None
    try:
        if v and v.startswith("P:"):
            k = int(v.split(":", 1)[1])
            return (
                _render_left(ps or []),
                _render_right(ps or [], (k, None)),
                _render_reason(ps or [], (k, None)),
                gr.update(value=str(k + 1)),
            )
        if v and v.startswith("S:"):
            _t, a, b = v.split(":")
            k, l = int(a), int(b)
            info = _compute_contra_terms_for_focus(
                ps or [], (k, l), bool(use_llm_contra), contra_model_id or "gpt-4o-mini"
            )
            if not info:
                return (
                    _render_left(ps or []),
                    _render_right(ps or [], (k, l)),
                    _render_reason(ps or [], (k, l)),
                    gr.update(value=str(k + 1)),
                )
            terms = info["terms"]
            rj = info["right_idx"]
            return (
                _render_left(ps or [], (k, l), terms),
                _render_right(ps or [], (k, l), terms, rj),
                _render_reason(ps or [], (k, l)),
                gr.update(value=str(k + 1)),
            )
    except Exception:
        pass
    return (
        _render_left(ps or []),
        _render_right(ps or [], (k, l)),
        _render_reason(ps or [], (k, l)),
        gr.update(value=str(k + 1)),
    )


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
                with gr.Column(scale=3):
                    left_html = gr.HTML(
                        label="Document A (claims)", value="", elem_id="left_pane"
                    )
                with gr.Column(scale=2):
                    right_html = gr.HTML(
                        label="Document B (matches)", value="", elem_id="right_pane"
                    )
                    reason_html = gr.HTML(
                        label="Reasoning", value="", elem_id="reason_box"
                    )
                with gr.Row():
                    use_llm_contra = gr.Checkbox(
                        value=True, label="Use LLM to extract contradicting terms"
                    )
                    contra_model = gr.Textbox(
                        value="gpt-4o-mini", label="Model for term extraction", scale=2
                    )

            pair_picker = gr.Radio(
                choices=[],
                value=None,
                label="Show Document B for paragraph…",
                interactive=True,
            )
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
                choices = [str(i + 1) for i in range(len(pairs))]
                default = choices[0] if choices else None
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
                    gr.update(choices=choices, value=default, interactive=True),
                )

            def _run2(
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
                # reasoning is empty until a specific span is clicked
                reason = _render_reason(pairs or [], (0, None))

                # Prepare Radio choices "1..N"
                choices = [str(i + 1) for i in range(len(pairs))]
                default = choices[0] if choices else None

                return (
                    left,  # left_html
                    right,  # right_html
                    reason,  # reason_html
                    pairs,  # pairs_state
                    align_path,  # align_path_state
                    pairs_path,  # pairs_path_state
                    gr.update(
                        value=json.loads(preview), visible=False
                    ),  # artifacts_json
                    gr.update(
                        choices=choices, value=default, interactive=True
                    ),  # pair_picker
                )

            run_btn.click(
                _run2,
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
                    reason_html,
                    pairs_state,
                    align_path_state,
                    pairs_path_state,
                    artifacts_json,
                    pair_picker,
                ],
            )

            def _export(p):
                if not p:
                    return gr.update(visible=False)
                return gr.update(value=p, visible=True)

            run_btn.click(_export, inputs=pairs_path_state, outputs=dl_pairs)
            pair_picker.change(
                _on_pick,
                inputs=[pairs_state, pair_picker],
                outputs=[left_html, right_html, reason_html],
            )
            # connect bridge
            bridge_click.change(
                _bridge_update,
                inputs=[pairs_state, bridge_click],
                outputs=[left_html, right_html, reason_html, pair_picker],
            )
            # react to `input` events (what JS emits)
            bridge_click.input(
                _bridge_combo,
                inputs=[pairs_state, bridge_click, use_llm_contra, contra_model],
                outputs=[left_html, right_html, reason_html, pair_picker],
            )

# Fast launch guard
if __name__ == "__main__":
    demo.launch(show_error=True)
