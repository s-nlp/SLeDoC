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
    find_best_matches_with_window,
    get_paragraphs_from_docx,
    merge_incomplete_sentences,
    separate_points,
)

# Stage 1
from app.claim_extractor import DEFAULT_SYSTEM_PROMPT, run_claim_extraction
from app.config import LLM_NLI_SYSTEM_PROMPT

# Stage 2
from app.nli_predict import _list_models, run_nli_file
from app.openai_client import make_client

# Stage 1+2 via LLM
from app.pipeline_llm import run_llm_nli_file

# Shared UI assets
from app.settings import BASE_CSS, CUSTOM_JS, SIDEBAR_CSS, nav_tag

# Styling
EXTRA_CSS = (
    BASE_CSS
    + SIDEBAR_CSS
    + """
/* dual-pane viewer layout */
.left-pane  { flex: 2 1 0; min-width: 420px; }
.right-pane { flex: 1 1 0; position: static; max-height: 80vh; overflow:auto; }
#viewer_row { align-items: stretch; }
#left_pane, #right_pane { display: block; }

/* paragraph card: compact, borderless, lightly indented with spacing */
.para-box{
  border: 0;
  padding: 4px 0 10px 8px;      /* small left indent + breathing room */
  margin: 12px 0;               /* visible separation between paragraphs */
  background: transparent;      /* no box background */
  box-shadow: none;             /* no shadow */
}
.para-head { display:none; }    /* hide the "Document A — paragraph N" header */
.para-inner { line-height: 1.45; }

/* claim spans */
.hl{ position:relative; padding:0 3px; border-radius:5px; cursor:pointer; }
.hl:hover { outline:1px dashed #888; }

/* NLI colors — keep them faint */
.hl.entailment     { background: rgba(34,197,94,.18); }   /* green */
.hl.neutral        { background: rgba(59,130,246,.18); }  /* blue */
.hl.contradiction  { background: rgba(244,63,94,.18); }

/* contradiction term highlight */
.contra-term{ background: #fff59a; padding:0 2px; border-radius:3px; }

/* selected state: strong outline, keep original background color */
.hl.selected { outline:2px solid #000 !important; }

/* mute tooltip artifacts */
.hl::after { display:none !important; }

/* make the right column cards use the same vertical spacing as the left */
.mirror-box{
  border:1px solid #adb5bd;
  padding:12px; 
  border-radius:12px;
  background:#fafafa;
  min-height:140px;
  margin:12px 0;
}
/* ensure the very first cards start at the same top edge */
.left-pane  .para-box:first-child,
.right-pane .mirror-box:first-child {
  margin-top: 0;
}

/* optional: stretch both columns to the same overall height */
.viewer-wrap { display:flex; gap:16px; align-items:stretch; }

/* left column title */
.anch{ font-size:11px; opacity:.8; margin-left:4px; text-decoration:none; }

/* legend + confidence UI */
.toolbar { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin:8px 0; }
.legend { display:flex; gap:12px; align-items:center; font-size:12px; color:#475569; }
.legend .key { display:inline-flex; align-items:center; gap:6px; }
.legend .dot { width:10px; height:10px; border-radius:2px; display:inline-block; }
.legend .dot.ent { background:#22c55e; } /* entailment */
.legend .dot.con { background:#f43f5e; } /* contradiction */
.legend .dot.neu { background:#3b82f6; } /* addition/neutral */

/* dynamic heights */
.para-box{ min-height: unset; }
.mirror-box{ min-height: unset; }

/* right pane: independent scroller */
#right_pane { 
  position: static;
  max-height: 80vh;
  overflow-y: auto;
}

/* reasoning panel — tighter to right pane, bolder, larger text */
.reason-wrap {
  margin-top: 4px;                 /* closer to right pane content */
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.reason-title {
  font-weight: 800;
  margin: 3px 0 3px;
  font-size: 16px;
}
.reason-card {
  border: 2px solid #334155;       /* solid, visible */
  background: #ffffff;
  padding: 10px 12px;
  border-radius: 12px;
  font-size: 16px;                 /* bigger text */
  font-weight: 600;                /* bold content */
  box-shadow: 0 2px 6px rgba(0,0,0,.06);
}

/* contradiction focus box */
.contra-box { margin-top:10px;padding:10px;border:1px solid #e5e7eb;border-radius:10px;background:#fafafa }
.contra-head { font-weight:600;margin-bottom:6px }
.contra-row { display:flex;gap:8px;align-items:flex-start;margin:4px 0 }
.side-tag { font-size:12px;color:#6b7280;padding:2px 6px;border:1px solid #e5e7eb;border-radius:9999px }
.side-pills { display:flex;gap:6px;flex-wrap:wrap }
.pill { display:inline-block;padding:2px 8px;border:1px solid #d1d5db;border-radius:9999px;background:white;font-size:12px }
.contra-src { margin-top:8px;font-size:12px;color:#6b7280;display:grid;gap:2px }
.src-tag { font-weight:600;color:#4b5563 }

/* Make the left pane feel like a single “big box” of Document A */
.left-pane {
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 8px;
    background: #fff;
    max-height: 80vh;       /* left pane its own scroller */
    overflow-y: auto;
}
.left-pane .para-box { margin: 8px 0; }

/* left column title */
.left-title{
  font-weight:700;
  font-size:14px;
  color:#334155;
  margin:4px 4px 10px 4px;
  opacity:.9;
}

/* right column title */
.right-title{
  font-weight:700;
  font-size:14px;
  color:#334155;
  margin:4px 4px 10px 4px;
  opacity:.9;
}

/* Dimming behavior for left pane */
.left-pane .para-box.para-focus { outline: 2px solid #334155; }
.left-pane .para-box.para-dim   { opacity: .55; filter: saturate(.6); }
"""
)


# Helpers
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


def _get_precomputed_contra(pairs, k: int, i_left: int):
    """Return cached {'terms': [...], 'right_idx': j} for given left span if available."""
    if not pairs or k is None or i_left is None:
        return None
    b = pairs[k]
    cache = b.get("_contra_cache") or {}
    return cache.get(i_left)


def _precompute_contra_terms_for_all(pairs, use_llm: bool, model_id: str):
    """
    For each block and each left claim that has at least one 'contradiction' link,
    compute contradicting terms once and cache them on the block:
      block['_contra_cache'][i_left] = { 'terms': {...}, 'right_idx': int }
    """
    if not pairs:
        return pairs

    for k, b in enumerate(pairs):
        links, _ = _link_map_for_pair(b)
        out1 = b.get("output_1") or []
        out2 = b.get("output_2") or []
        if not links or not out1 or not out2:
            continue

        cache = b.get("_contra_cache") or {}
        for i_left, lst in links.items():
            # find the first contradiction right-idx (or choose best if you prefer)
            rj = None
            for ridx, lbl in lst:
                if str(lbl).lower() == "contradiction":
                    rj = ridx
                    break
            if rj is None:
                continue
            if i_left in cache:
                continue  # already computed

            left = str(out1[i_left].get("claim") or out1[i_left].get("input") or "")
            right = str(out2[rj].get("claim") or out2[rj].get("input") or "")

            terms = _get_contra_terms(
                left, right, use_llm=use_llm, model_id=model_id or "gpt-4o"
            )
            cache[i_left] = {"terms": terms, "right_idx": rj}

        if cache:
            b["_contra_cache"] = cache
    return pairs


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
        left, right, use_llm=use_llm, model_id=model_id or "gpt-4o"
    )
    return {"terms": terms, "right_idx": rj}


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
        # '<div id="conf_box">Confidence: —</div>'
        '<div class="legend">'
        '<span class="key"><span class="dot ent"></span> entailment (equivalent)</span>'
        '<span class="key"><span class="dot con"></span> contradiction</span>'
        '<span class="key"><span class="dot neu"></span> addition (neutral)</span>'
        "</div>"
        "</div>"
    )


# Renderers
def _render_left(
    blocks: List[Dict[str, Any]],
    focus: Optional[Tuple[int, Optional[int]]] = None,
    contra_terms: Optional[Dict[str, List[str]]] = None,
) -> str:
    """
    Big left pane: for each pair, show Document A claims as spans, colored by worst NLI link.
    If no claims available for a block, fall back to raw paragraph text.
    """
    html_parts = ['<div class="viewer-wrap"><div class="left-pane">']
    html_parts = [
        '<div class="viewer-wrap"><div class="left-pane">',
        '<div class="left-title">Source text of Document A</div>',
    ]

    for pi, b in enumerate(blocks):
        out1 = b.get("output_1") or []
        links, left_color = _link_map_for_pair(b)

        if out1:
            # severity order
            sev_rank = {"contradiction": 3, "neutral": 2, "entailment": 1}

            spans = []
            for i1, c in enumerate(out1):
                raw = str(c.get("claim") or c.get("input") or "")

                # choose best right idx by severity for this left i1 (if any)
                best_r = None
                best_lbl = ""
                for rj, lbl in links.get(i1, []):
                    if best_r is None or sev_rank.get(lbl, 0) > sev_rank.get(
                        best_lbl, 0
                    ):
                        best_r = rj
                        best_lbl = lbl or ""

                # term highlighting if this left is focused
                if focus and focus[0] == pi and focus[1] == i1 and contra_terms:
                    txt = _wrap_terms_html(raw, (contra_terms.get("from_span_1") or []))
                else:
                    txt = _escape(raw)

                # NLI color for the left span (worst label among its links)
                cls = "hl " + (left_color.get(i1, "") or "")

                # add target/hcolor so left can point to right
                target_attr = (
                    f' data-target="R-{pi}-{best_r}"' if best_r is not None else ""
                )
                hcolor_attr = (
                    f' data-hcolor="{_hover_color(best_lbl)}"'
                    if best_r is not None
                    else ""
                )

                spans.append(
                    f'<span id="L-{pi}-{i1}" class="{cls}" data-pair="{pi}" data-left="{i1}"{target_attr}{hcolor_attr}>{txt}</span>'
                )
            inner = "<br>".join(spans)
        else:
            inner = _escape(_text_left(b))

        html_parts.append(
            f"""
            <div class="para-box para-compact" data-idx="{pi}">
                <div class="para-inner">{inner}</div>
            </div>
        """
        )

    html_parts.append("</div>")  # left-pane
    html_parts.append("</div>")  # viewer-wrap
    return "\n".join(html_parts)


REASON_BY_LABEL = {
    "equivalent": "спаны идентичны",
    "entailment": "спаны идентичны",
    "contradiction": "противоречие между утверждениями",
    "addition": "дополнение / новая информация",
    "neutral": "дополнение / новая информация",
}


def _hover_color(lbl: str) -> str:
    # Match your left-side hover palette as close as possible
    PALETTE = {
        "contradiction": "#ffd6c2",  # soft red-ish
        "neutral": "#fff3a0",  # yellow
        "entailment": "#d6ffd6",  # soft green
    }
    return PALETTE.get(lbl or "", "#fff3a0")  # default to yellow


def _render_right_col(
    blocks: List[Dict[str, Any]],
    focus: Tuple[int, Optional[int]],
    contra_terms: Optional[Dict[str, List[str]]] = None,
    target_right_idx: Optional[int] = None,
) -> str:
    """
    Static right column (independent scroller). No floating alignment.
    Shows Document B claims for the selected pair (and, if a left span is selected,
    prioritizes/annotates the linked right spans).
    """
    if not blocks:
        return (
            '<div class="right-pane-inner">'
            '<div class="right-title">Snippet of text in Document B</div>'
            '<div class="mirror-box">—</div>'
            '</div>'
        )

    k, i_left = focus
    k = max(0, min(k, len(blocks) - 1))
    b = blocks[k]

    out2 = b.get("output_2") or []
    links, _left_color = _link_map_for_pair(b)

    # severity for deciding "worst" label per right span
    severity = {"contradiction": 3, "neutral": 2, "entailment": 1}
    label_for_right: Dict[int, str] = {}

    def take_worst(cur: str, new: str) -> str:
        return new if severity.get(new, 0) > severity.get(cur or "", 0) else cur

    if i_left is None:
        for li, pairs in links.items():
            for rj, lbl in pairs:
                label_for_right[rj] = take_worst(label_for_right.get(rj, ""), str(lbl).lower())
        right_order = sorted(label_for_right.keys()) if label_for_right else list(range(len(out2)))
    else:
        for rj, lbl in links.get(i_left, []):
            label_for_right[rj] = take_worst(label_for_right.get(rj, ""), str(lbl).lower())
        right_order = sorted(label_for_right.keys())

    # Map each right span to its "best" left mate for hover sync
    best_for_right: Dict[int, Tuple[int, str]] = {}
    if i_left is None:
        for li, pairs in links.items():
            for rj, lbl in pairs:
                prev = best_for_right.get(rj)
                if prev is None or severity.get(lbl, 0) > severity.get(prev[1], 0):
                    best_for_right[rj] = (li, lbl)
    else:
        for rj, lbl in links.get(i_left, []):
            prev = best_for_right.get(rj)
            if prev is None or severity.get(lbl, 0) > severity.get(prev[1], 0):
                best_for_right[rj] = (i_left, lbl)

    # Optional anchor indicators (for neutral/addition with anchor on left)
    anchor_for_right: Dict[int, str] = {}
    for rr in b.get("nli_results") or []:
        lblr = str(rr.get("label") or "").lower()
        if lblr in ("neutral", "addition"):
            hyp = str(rr.get("hypothesis_raw") or rr.get("hypothesis") or "")
            anc = rr.get("anchor")
            if anc is None:
                continue
            for jj, cc in enumerate(out2):
                txtj = str(cc.get("claim") or cc.get("input") or "")
                if txtj.strip() == hyp.strip():
                    if "output_1" in b:
                        raw_anchor = (b.get("output_1") or [])[anc]
                        anchor_for_right[jj] = str(
                            raw_anchor.get("claim") or raw_anchor.get("input") or ""
                        )
                    break

    # Build the right body
    if out2 and right_order:
        spans = []
        for j in right_order:
            if not (0 <= j < len(out2)):
                continue
            c = out2[j]
            raw = str(c.get("claim") or c.get("input") or "")

            # highlight contradicting terms only for the target right span, if provided
            if target_right_idx is not None and j == int(target_right_idx) and contra_terms:
                txt = _wrap_terms_html(raw, (contra_terms or {}).get("from_span_2") or [])
            else:
                txt = _escape(raw)

            lbl = (label_for_right.get(j, "") or "").lower()
            cls = "hl " + (lbl if lbl in ("contradiction","neutral","entailment") else "")

            li_for_j = best_for_right.get(j)
            if li_for_j:
                li_idx, lbl_for_j = li_for_j
                target_attr = f' data-target="L-{k}-{li_idx}"'
                hcolor_attr = f' data-hcolor="{_hover_color(lbl_for_j)}"'
            else:
                target_attr = ""
                hcolor_attr = f' data-hcolor="{_hover_color(lbl or "neutral")}"'

            anchor_sup = ""
            if j in anchor_for_right:
                anchor_sup = f' <sup class="anch" title="anchor: {_escape(anchor_for_right[j])}">🔗</sup>'

            spans.append(
                f'<span id="R-{k}-{j}" class="{cls}" data-pair="{k}" data-right="{j}"{target_attr}{hcolor_attr}>{txt}</span>{anchor_sup}'
            )
        body = "<br>".join(spans)
    else:
        body = _escape(_text_right(b))

    hdr = f"Document B — {'matching claims' if i_left is None else 'matching claims for selected span'} (pair {k+1})"

    return f"""
      <div class="right-pane-inner">
        <div class="right-title">Snippet of text in Document B</div>
        <div class="mirror-box" data-idx="{k}">
          <div class="para-head">{hdr}</div>
          <div>{body}</div>
        </div>
      </div>
    """


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

    return (
        '<div class="reason-wrap"><div class="reason-title"><b>Explanation</b></div>'
        + "".join(items)
        + "</div>"
    )


# Pipeline
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
        paragraphs_b = separate_points(
            merge_incomplete_sentences(get_paragraphs_from_docx(p2))
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
    right_html = _render_right_col(pairs, (0, None))

    return align_path, pairs_path, _preview, left_html, right_html, pairs


def _on_pick(pairs, choice):
    if not pairs:
        return (
            _render_left(
                [],
            ),
            _render_right_col([], (0, None)),
            _render_reason([], (0, None)),
        )
    try:
        idx = max(0, int(str(choice)) - 1) if choice else 0
    except Exception:
        idx = 0
    return (
        _render_left(pairs),
        _render_right_col(pairs, (idx, None)),
        _render_reason(pairs, (idx, None)),
    )


def _bridge_combo(ps, v, use_llm_contra=False, contra_model_id="gpt-4o"):
    k, l_ = 0, None
    try:
        if v and v.startswith("P:"):
            k = int(v.split(":", 1)[1])
            return (
                _render_left(ps or []),
                _render_right_col(ps or [], (k, None)),
                _render_reason(ps or [], (k, None)),
                gr.update(value=str(k + 1)),
            )
        if v and v.startswith("S:"):
            _t, a, b = v.split(":")
            k, l_ = int(a), int(b)
            info = _get_precomputed_contra(ps or [], k, l_)
            if not info:
                info = _compute_contra_terms_for_focus(
                    ps or [],
                    (k, l_),
                    bool(use_llm_contra),
                    contra_model_id or "gpt-4o",
                )
                # store back into cache so subsequent clicks are instant & stable
                if info:
                    block = (ps or [])[k]
                    cache = block.get("_contra_cache") or {}
                    cache[l_] = info
                    block["_contra_cache"] = cache
            terms = info["terms"]
            rj = info["right_idx"]
            return (
                _render_left(ps or [], (k, l_), terms),
                _render_right_col(ps or [], (k, l_), terms, rj),
                _render_reason(ps or [], (k, l_)),
                gr.update(value=str(k + 1)),
            )
    except Exception:
        pass
    return (
        _render_left(ps or []),
        _render_right_col(ps or [], (k, l_)),
        _render_reason(ps or [], (k, l_)),
        gr.update(value=str(k + 1)),
    )


# UI
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
                        value="gpt-4o", label="LLM model (for combined 1+2)"
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
                    use_llm_contra = gr.Checkbox(
                        value=True, label="Use LLM to extract contradicting terms"
                    )
                    contra_model = gr.Textbox(
                        value="gpt-4o", label="Model for term extraction", scale=2
                    )
                with gr.Row():
                    artifacts_json = gr.JSON(label="Artifacts", visible=False)

            run_btn = gr.Button("Run full pipeline", variant="primary")
            gr.HTML(_legend_html(), elem_id="viewer_legend")

            with gr.Row(elem_id="viewer_row"):
                with gr.Column(scale=2):
                    left_html = gr.HTML(
                        label="Document A (claims)", value="", elem_id="left_pane"
                    )
                with gr.Column(scale=2):
                    right_html = gr.HTML(
                        label="Document B (matches)", value="", elem_id="right_pane"
                    )
                    reason_html = gr.HTML(
                        label="Explanation", value="", elem_id="reason_box"
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
                use_llm_contra,
                contra_model,
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
                # Precompute contradiction terms once for all blocks so clicks are instant and stable
                try:
                    pairs = _precompute_contra_terms_for_all(
                        pairs,
                        bool(use_llm_contra),
                        (contra_model or "gpt-4o"),
                    )
                except Exception:
                    # fail-safe: keep pairs as-is
                    pass

                # reasoning is empty until a specific span is clicked
                reason = _render_reason(pairs or [], (0, None))

                # Prepare Radio choices "1..N"
                choices = [str(i + 1) for i in range(len(pairs))]
                default = choices[0] if choices else None

                return (
                    left,  # left_html
                    _render_right_col(
                        pairs, (0, None)
                    ),  # right_html (fresh, uses any precomputed cache)
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
                    use_llm_contra,
                    contra_model,
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
            # react to `input` events (what JS emits)
            bridge_click.input(
                _bridge_combo,
                inputs=[pairs_state, bridge_click, use_llm_contra, contra_model],
                outputs=[left_html, right_html, reason_html, pair_picker],
            )

# Fast launch guard
if __name__ == "__main__":
    demo.launch(show_error=True)
