import asyncio
import difflib
import hashlib
import html
import json
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zipfile import BadZipFile

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
from app.config import DEFAULT_MODEL, LLM_NLI_SYSTEM_PROMPT, LLM_NLI_SYSTEM_PROMPT_CODE

# Stage 2
from app.nli_predict import _list_models, run_nli_file
from app.openai_client import make_async_client

# Stage 1+2 via LLM
from app.pipeline_llm import run_llm_nli_file

# Shared UI assets
from app.settings import (
    BASE_CSS,
    CUSTOM_JS,
    HOVER_PALETTE,
    NLI_REASON_BY_LABEL,
    NLI_SEVERITY,
    SIDEBAR_CSS,
    VIEWER_CSS,
    nav_tag,
)

# Styling
TOOLBAR_CSS = """
  #legend_row { align-items: center; }
  #legend_right { margin-left: auto; display: flex; gap: 8px; align-items: center; }
  /* make buttons compact */
  #swap_button { min-width: 0; padding: 6px 10px; font-size: 0.9rem; }
  #dl_labels_btn .gr-button { min-width: 0; padding: 6px 10px; font-size: 0.9rem; }
"""
EXTRA_CSS = BASE_CSS + SIDEBAR_CSS + VIEWER_CSS + TOOLBAR_CSS


# Helpers
def _escape(s: str) -> str:
    return html.escape(s or "", quote=False).replace("\n", "<br>")


def _norm(s: str) -> str:
    """Normalize for robust text matching: collapse spaces and casefold."""
    return re.sub(r"\s+", " ", (s or "")).strip().casefold()


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
MIN_TERM_ALNUM_LEN = 2  # require ≥2 alnum chars to highlight (to avoid 'в', 'и', etc)
MODELS_LIST = _list_models()


def _alnum_len(s: str) -> int:
    # count letters/digits/underscore in Unicode
    return len(re.sub(r"[^\w]", "", s, flags=re.UNICODE))


def _anchor_as_int(x) -> Optional[int]:
    try:
        if isinstance(x, str):
            x = x.strip()
        ai = int(x)
        return ai
    except Exception:
        return None


def _compute_diff_mask(a: str, b: str) -> List[bool]:
    """
    Return a boolean mask for `a` (len == len(a)) where True marks positions that
    are *different* from `b` (by difflib at char level, case-insensitive).
    Equal blocks are False; replace/delete blocks are True; inserts in `b` do not
    affect the mask for `a`.
    """
    a0, b0 = (a or ""), (b or "")
    sm = difflib.SequenceMatcher(a=a0.lower(), b=b0.lower())
    mask = [True] * len(a0)
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag == "equal":
            for i in range(i1, i2):
                mask[i] = False
    return mask


def _read_paragraphs_generic(p: Path, is_code: bool) -> list[str]:
    """
    - If it's a real .docx AND we're not in code mode, use the existing docx pipeline.
    - Otherwise read as UTF-8 text and split into blank-line separated blocks (keeps indentation).
    - If .docx load fails (e.g., mislabeled path), gracefully fall back to text.
    """
    if (not is_code) and p.suffix.lower() == ".docx":
        try:
            return separate_points(
                merge_incomplete_sentences(get_paragraphs_from_docx(p))
            )
        except BadZipFile:
            # mislabeled file; read as text below
            pass
        except Exception:
            # any unexpected docx error → treat as text
            pass

    # Text/code path
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        text = p.read_bytes().decode("utf-8", errors="ignore")

    blocks: list[str] = []
    buf: list[str] = []
    for line in text.splitlines():
        if line.strip() == "":
            if buf:
                blocks.append("\n".join(buf).rstrip())
                buf = []
        else:
            buf.append(line.rstrip())
    if buf:
        blocks.append("\n".join(buf).rstrip())

    return [b for b in blocks if b.strip()] or [text.strip()]


def _wrap_terms_html(
    text: str, terms: List[str], allowed_mask: Optional[List[bool]] = None
) -> str:
    """
    Wrap selected terms/phrases in <mark class="contra-term">…</mark>, **merging**
    adjacent matches if separated only by whitespace. This way tokens like
    ['blow','my','mind'] become a single marked phrase “blow my mind”.
    """
    if not text:
        return ""
    if not terms:
        return _escape(text)

    # normalize, de-dup, filter
    cleaned, seen = [], set()
    for t in sorted((t or "").strip() for t in terms if t):
        if not t:
            continue
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        if k in RUS_STOPWORDS_SHORT:
            continue
        if _alnum_len(t) < MIN_TERM_ALNUM_LEN:
            continue
        cleaned.append(t)
    if not cleaned:
        return _escape(text)

    # whole-token regex for each term/phrase
    alts = [
        rf"(?<!\w){re.escape(t)}(?!\w)" for t in sorted(cleaned, key=len, reverse=True)
    ]
    pattern = "(?:" + "|".join(alts) + ")"
    try:
        rx = re.compile(pattern, flags=re.IGNORECASE | re.UNICODE)
    except Exception:
        return _escape(text)

    # collect raw matches (start, end), optionally filter by allowed_mask
    matches = []
    for m in rx.finditer(text):
        s, e = m.span()
        if allowed_mask and len(allowed_mask) == len(text):
            # keep only if ANY char in [s:e) lies in a "different" region
            if not any(allowed_mask[i] for i in range(s, e)):
                continue
        matches.append((s, e))
    if not matches:
        return _escape(text)
    merged: List[Tuple[int, int]] = []
    s0, e0 = matches[0]
    for s, e in matches[1:]:
        gap = text[e0:s]
        gap_stripped = gap.strip()
        # merge if the gap is:
        #   - only whitespace, OR
        #   - whitespace + exactly one symbol
        if (not gap) or (
            gap_stripped == "" or re.fullmatch(r"[,.:;!?–—-]", gap_stripped)
        ):
            e0 = e  # include the gap (spaces + the one symbol) inside the marked region
        else:
            merged.append((s0, e0))
            s0, e0 = s, e
    merged.append((s0, e0))

    # build HTML with escapes, marking merged segments
    out, last = [], 0
    for s, e in merged:
        if s > last:
            out.append(_escape(text[last:s]))
        out.append(f'<mark class="contra-term">{_escape(text[s:e])}</mark>')
        last = e
    if last < len(text):
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
        s = _get_claim_text(c, strip=True)
        if s:
            idx[s] = i
    return idx


def _get_claim_text(claim: Dict[str, Any], *, strip: bool = False) -> str:
    text = str(claim.get("claim") or claim.get("input") or "")
    return text.strip() if strip else text


def _entailment_maps(block: Dict[str, Any]) -> Tuple[Dict[int, int], Dict[int, int]]:
    """
    Return two maps based on entailment/equivalent links only:
      ent_L_to_R[left_idx]  = right_idx
      ent_R_to_L[right_idx] = left_idx
    We pick the first seen mate per side for stability.
    """
    out1 = block.get("output_1") or []
    out2 = block.get("output_2") or []
    idx1 = _index_claims(out1)
    idx2 = _index_claims(out2)
    ent_L_to_R: Dict[int, int] = {}
    ent_R_to_L: Dict[int, int] = {}
    for r in block.get("nli_results") or []:
        lbl = str(r.get("label") or "").lower()
        if lbl not in ("entailment", "equivalent"):
            continue
        prem = str(r.get("premise_raw") or r.get("premise") or "")
        hyp = str(r.get("hypothesis_raw") or r.get("hypothesis") or "")
        li = idx1.get(prem)
        rj = idx2.get(hyp)
        if li is None or rj is None:
            li = idx1.get(hyp)
            rj = idx2.get(prem)
        if li is None or rj is None:
            continue
        if li not in ent_L_to_R:
            ent_L_to_R[li] = rj
        if rj not in ent_R_to_L:
            ent_R_to_L[rj] = li
    return ent_L_to_R, ent_R_to_L


def _best_right_for_left_anchor(
    block: Dict[str, Any], li_anchor: int
) -> Tuple[Optional[int], str]:
    """
    For a given LEFT anchor index, pick the RIGHT mate and label to drive the bracket color:
      - prefer 'contradiction' if any exists,
      - else 'entailment'/'equivalent' if exists,
      - else (None, '').
    """
    out1 = block.get("output_1") or []
    out2 = block.get("output_2") or []
    if not (0 <= li_anchor < len(out1)):
        return None, ""
    idx1 = _index_claims(out1)
    idx2 = _index_claims(out2)
    best_contra: Optional[int] = None
    best_ent: Optional[int] = None
    for r in block.get("nli_results") or []:
        prem = str(r.get("premise_raw") or r.get("premise") or "")
        hyp = str(r.get("hypothesis_raw") or r.get("hypothesis") or "")
        lab = str(r.get("label") or "").lower()
        # map to indices (either orientation)
        li = idx1.get(prem, None)
        rj = idx2.get(hyp, None)
        if li is None or rj is None:
            li = idx1.get(hyp, None)
            rj = idx2.get(prem, None)
        if li != li_anchor or rj is None:
            continue
        if lab == "contradiction" and best_contra is None:
            best_contra = rj
        elif lab in ("entailment", "equivalent") and best_ent is None:
            best_ent = rj
    if best_contra is not None:
        return best_contra, "contradiction"
    if best_ent is not None:
        return best_ent, "entailment"
    return None, ""


def _build_addition_anchors(
    block: Dict[str, Any],
) -> Tuple[
    Dict[int, int],  # left_addition_anchor[left_idx] -> left_anchor_idx
    Dict[int, int],  # right_add_to_left_anchor[right_idx] -> left_anchor_idx
    Dict[int, int],  # right_add_to_right_anchor[right_idx] -> right_anchor_idx
    Dict[str, int],  # right_text_to_left_anchor[normed_right_text] -> left_anchor_idx
    Dict[
        int, Tuple[Optional[int], str]
    ],  # left_anchor_to_right_anchor[left_anchor_idx] -> (right_idx or None, label_for_brackets)
    Dict[int, int],  # left_add_to_right_add[left_idx_addition] -> right_idx_addition
]:
    """
    Returns four maps:
      1) left_addition_anchor[left_idx] -> left_anchor_idx
      2) right_addition_to_left_anchor[right_idx] -> left_anchor_idx
      3) right_addition_to_right_anchor[right_idx] -> right_anchor_idx (if anchor text exists on B)
      4) right_text_to_left_anchor[normed_right_text] -> left_anchor_idx (when right_idx could not be resolved)
      5) left_anchor_to_right_anchor[left_anchor_idx] -> (right_idx or None, label_for_brackets)
      6) left_add_to_right_add[left_idx_addition] -> right_idx_addition (if both sides are mapped)

    We use:
      - r['anchor'] when present (index into left/output_1),
      - fallback: treat the matched left span as anchor,
      - and try to find the *same* anchor text among right/output_2 claims.
    """
    out1 = block.get("output_1") or []
    out2 = block.get("output_2") or []
    idx1 = _index_claims(out1)
    idx2 = _index_claims(out2)
    # normalized indexes help when LLM changes case/whitespace
    idx1_norm = {_norm(_get_claim_text(c)): i for i, c in enumerate(out1 or [])}
    ent_L_to_R, ent_R_to_L = _entailment_maps(block)

    left_addition_anchor: Dict[int, int] = {}
    right_add_to_left_anchor: Dict[int, int] = {}
    right_add_to_right_anchor: Dict[int, int] = {}
    right_text_to_left_anchor: Dict[str, int] = {}
    left_anchor_to_right_anchor: Dict[int, Tuple[Optional[int], str]] = {}
    left_add_to_right_add: Dict[int, int] = {}

    # Pre-compute sorted right indices that have any entailment (for "closest green before" fallback)
    ent_right_idxs_sorted = sorted(ent_R_to_L.keys())
    # Normalized index for right claim text → j
    idx2_norm = {_norm(_get_claim_text(c)): j for j, c in enumerate(out2 or [])}

    for r in block.get("nli_results") or []:
        lbl = str(r.get("label") or "").lower()
        if lbl not in ("neutral", "addition"):
            continue
        prem = str(r.get("premise_raw") or r.get("premise") or "")
        hyp = str(r.get("hypothesis_raw") or r.get("hypothesis") or "")
        # Robust mapping: either side may be empty / swapped for additions
        li = (
            idx1.get(prem) if prem in idx1 else (idx1.get(hyp) if hyp in idx1 else None)
        )
        rj = (
            idx2.get(hyp) if hyp in idx2 else (idx2.get(prem) if prem in idx2 else None)
        )
        # If we still have no rj, try to map by normalized right text
        if rj is None:
            # prefer the text that belongs to the right side (hypothesis in our pipeline)
            cand = hyp if hyp not in (None, "") else prem
            nj = idx2_norm.get(_norm(cand))
            if nj is not None:
                rj = nj
        # Likewise, if li is None, try normalized lookup on the left
        if li is None:
            candL = prem if prem not in (None, "") else hyp
            li = idx1_norm.get(_norm(candL))

        anc_li: Optional[int] = r.get("anchor")
        if not isinstance(anc_li, int) or not (0 <= int(anc_li) < len(out1)):
            anc_li = None

        # 1) prefer explicit LLM-provided anchor
        # 2) else: if THIS right span entails a left → use that
        if anc_li is None and rj is not None:
            anc_li = ent_R_to_L.get(rj)

        # 3) else: choose the CLOSEST entailing right — prefer previous; if none, take next
        if anc_li is None and ent_right_idxs_sorted:
            prevs = [x for x in ent_right_idxs_sorted if (rj is None or x < rj)]
            nexts = [x for x in ent_right_idxs_sorted if (rj is None or x > rj)]
            j0 = prevs[-1] if prevs else (nexts[0] if nexts else None)
            if j0 is not None:
                anc_li = ent_R_to_L.get(j0)
                # also keep that RIGHT j0 as the right-side in-pane anchor
                if anc_li is not None:
                    right_add_to_right_anchor[rj if rj is not None else j0] = j0

        # 4) last resort: pick the closest LEFT span.
        #    If the addition is the FIRST sentence → pick the NEXT one.
        if anc_li is None and out1:
            if li is not None:
                if li > 0:
                    anc_li = li - 1
                elif li + 1 < len(out1):
                    anc_li = li + 1
                else:
                    anc_li = 0
            else:
                # no left mapping at all: prefer index 1 if exists (treat as "first addition")
                anc_li = 1 if len(out1) > 1 else 0

        # Decide RIGHT-side anchor for brackets using the anchor's *own* best link (contra > ent)
        anc_rj: Optional[int] = None
        anc_lbl: str = ""
        if anc_li is not None:
            anc_rj, anc_lbl = _best_right_for_left_anchor(block, anc_li)
            # Fallback: if the left anchor has no contra/ent mate, use THIS pair's right as the in-pane anchor
            if (anc_rj is None) and (rj is not None):
                anc_rj = rj
                # if there was no strong label, default bracket/background feel to entailment-green
                if not anc_lbl:
                    anc_lbl = "entailment"
            # Ensure we always record *some* right anchor for the left anchor (even if it's the addition mate itself)
            if anc_li not in left_anchor_to_right_anchor:
                left_anchor_to_right_anchor[anc_li] = (anc_rj, anc_lbl)
            else:
                # upgrade empty mapping (None, "") if we now have a concrete right anchor
                _old_rj, _old_lbl = left_anchor_to_right_anchor[anc_li]
                if _old_rj is None and anc_rj is not None:
                    left_anchor_to_right_anchor[anc_li] = (anc_rj, anc_lbl)
        # if not found yet but we left a right-side anchor above, keep it
        if anc_rj is None and rj is not None and rj in right_add_to_right_anchor:
            anc_rj = right_add_to_right_anchor[rj]

        # Mark additions on the LEFT. Include self-anchored (li == anc_li) so left-click can trigger delta.
        if anc_li is not None and li is not None:
            left_addition_anchor[li] = int(anc_li)
        # If this (li, rj) is an explicit addition pair, remember the direct mate
        if anc_li is not None and li is not None and rj is not None:
            left_add_to_right_add[li] = int(rj)
        if anc_li is not None and rj is not None:
            right_add_to_left_anchor[rj] = int(anc_li)
        # If we couldn't resolve rj but do have the text → keep a text→anchor map
        if anc_li is not None and rj is None:
            cand = hyp if hyp not in (None, "") else prem
            if cand:
                right_text_to_left_anchor[_norm(cand)] = int(anc_li)
        # always keep a right→right anchor, even if it points to self (harmless; JS ignores equality)
        if anc_rj is not None and rj is not None:
            right_add_to_right_anchor[rj] = int(anc_rj)

    return (
        left_addition_anchor,
        right_add_to_left_anchor,
        right_add_to_right_anchor,
        right_text_to_left_anchor,
        left_anchor_to_right_anchor,
        left_add_to_right_add,
    )


# cache to avoid repeat calls for same (left,right)
_CONTRA_CACHE: Dict[str, Dict[str, List[str]]] = {}
_DELTA_CACHE: Dict[str, Dict[str, List[str]]] = {}  # for addition “delta” terms


@lru_cache(maxsize=4096)
def _hash_pair(a: str, b: str) -> str:
    return hashlib.sha1((a + "␞" + b).encode("utf-8")).hexdigest()


async def _llm_delta_terms_async(
    span_1: str, span_2: str, model_id: str
) -> Dict[str, List[str]]:
    """
    Ask LLM for the ADDED words/phrases (delta) between span_1 (anchor) and span_2 (addition).
    Returns {"from_span_1":[...], "from_span_2":[...]} where from_span_2 should primarily contain
    the new info present in span_2 but absent in span_1. Fallback: token diff.
    """
    try:
        client, mid = make_async_client(model_id)
        prompt = (
            "Two spans describe the same fact, but span_2 contains ADDITIONAL details.\n"
            "Extract SHORT key words/phrases (1–4 words) that occur in one span and not the other.\n"
            "- Focus on NEW pieces in span_2 vs span_1 (list them under from_span_2).\n"
            "- Remove stopwords, keep noun/NP-ish or numeric tokens if possible.\n"
            "- Lowercase; no punctuation-only items.\n"
            "Return JSON ONLY:\n"
            '{"from_span_1": ["..."], "from_span_2": ["..."]}\n'
            "No commentary.\n\n"
            f"span_1 (anchor): {span_1}\n"
            f"span_2 (addition): {span_2}\n"
        )
        try:
            resp = await client.chat.completions.create(
                model=mid,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.01,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content or "{}")
        finally:
            try:
                closer = getattr(client, "aclose", None) or getattr(
                    client, "close", None
                )
                if closer:
                    res = closer()
                    if asyncio.iscoroutine(res):
                        await res
            except Exception:
                pass
        a = [str(x).strip() for x in data.get("from_span_1", []) if str(x).strip()]
        b = [str(x).strip() for x in data.get("from_span_2", []) if str(x).strip()]
        if not a and not b:
            raise ValueError("empty LLM delta result")
        return {"from_span_1": a, "from_span_2": b}
    except Exception:
        # Fallback: symmetric token diff (same as contradiction). Good enough to surface additions.
        return _fallback_contra_terms(span_1, span_2)


def _get_delta_terms(
    anchor_text: str, addition_text: str, use_llm: bool, model_id: str
):
    key = _hash_pair(anchor_text, addition_text) + (
        "#delta_llm" if use_llm else "#delta_diff"
    )
    if key in _DELTA_CACHE:
        return _DELTA_CACHE[key]
    if use_llm:
        result = _run_coro_sync(
            _llm_delta_terms_async(anchor_text, addition_text, model_id)
        )
    else:
        result = _fallback_contra_terms(anchor_text, addition_text)
    _DELTA_CACHE[key] = result
    return result


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
        client, mid = make_async_client(model_id)
        prompt = (
            "Here are two spans of a text that contradict each other.\n"
            "Your task: extract SHORT key words/phrases (1–4 words) that constitute the contradiction.\n"
            "Return JSON ONLY in this form:\n"
            '{"from_span_1": ["..."], "from_span_2": ["..."]}\n'
            "Do not add any commentary.\n\n"
            f"span_1: {left}\n"
            f"span_2: {right}\n"
        )
        try:
            resp = await client.chat.completions.create(
                model=mid,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.01,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content or "{}")
        finally:
            # Close the underlying httpx.AsyncClient before the loop is torn down.
            try:
                closer = getattr(client, "aclose", None) or getattr(
                    client, "close", None
                )
                if closer:
                    res = closer()
                    if asyncio.iscoroutine(res):
                        await res
            except Exception:
                pass
        # basic hygiene
        a = [str(x).strip() for x in data.get("from_span_1", []) if str(x).strip()]
        b = [str(x).strip() for x in data.get("from_span_2", []) if str(x).strip()]
        if not a and not b:
            raise ValueError("empty LLM result")
        return {"from_span_1": a, "from_span_2": b}
    except Exception:
        return _fallback_contra_terms(left, right)


# Run a coroutine regardless of current loop state; use a side thread if needed.
def _run_coro_sync(coro):
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            import threading

            box = {}

            def runner():
                box["res"] = asyncio.run(coro)

            t = threading.Thread(target=runner, daemon=True)
            t.start()
            t.join()
            return box.get("res")
    except RuntimeError:
        pass
    return asyncio.run(coro)


def _get_contra_terms(
    left: str, right: str, use_llm: bool, model_id: str
) -> Dict[str, List[str]]:
    key = _hash_pair(left, right) + ("#llm" if use_llm else "#diff")
    if key in _CONTRA_CACHE:
        return _CONTRA_CACHE[key]
    if use_llm:
        # Run safely even if an event loop is already running (e.g., inside Gradio)
        result = _run_coro_sync(_llm_contra_terms_async(left, right, model_id))
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

            left = _get_claim_text(out1[i_left])
            right = _get_claim_text(out2[rj])

            terms = _get_contra_terms(
                left, right, use_llm=use_llm, model_id=model_id or DEFAULT_MODEL
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
    left = _get_claim_text(out1[i_left])
    right = _get_claim_text(out2[rj])
    terms = _get_contra_terms(
        left, right, use_llm=use_llm, model_id=model_id or DEFAULT_MODEL
    )
    return {"terms": terms, "right_idx": rj}


def _map_record_indices(
    block: Dict[str, Any], r: Dict[str, Any]
) -> Tuple[Optional[int], Optional[int]]:
    """Map one nli_results record to (left_idx, right_idx) if possible (either orientation)."""
    out1 = block.get("output_1") or []
    out2 = block.get("output_2") or []
    idx1 = _index_claims(out1)
    idx2 = _index_claims(out2)
    prem = str(r.get("premise_raw") or r.get("premise") or "")
    hyp = str(r.get("hypothesis_raw") or r.get("hypothesis") or "")
    li = idx1.get(prem)
    rj = idx2.get(hyp)
    if li is None or rj is None:
        li = idx1.get(hyp)
        rj = idx2.get(prem)
    return li, rj


def _is_addition_pair(
    block: Dict[str, Any], li: Optional[int], rj: Optional[int]
) -> bool:
    """Return True if there exists an addition/neutral record that links left li and right rj in any orientation,
    or whose explicit anchor == li and maps to rj."""
    if rj is None:
        return False
    out1 = block.get("output_1") or []
    out2 = block.get("output_2") or []
    _ = _index_claims(out1)
    _ = _index_claims(out2)
    for rec in block.get("nli_results") or []:
        lab = str(rec.get("label") or "").lower()
        if lab not in ("addition", "neutral"):
            continue
        li2, rj2 = _map_record_indices(block, rec)
        if li is not None and li2 == li and rj2 == rj:
            return True
        # explicit anchor == li and right maps to rj
        anc = rec.get("anchor")
        if isinstance(anc, int) and li is not None and anc == li and rj2 == rj:
            return True
    return False


def _is_self_anchor_addition(
    block: Dict[str, Any], li: Optional[int], rj: Optional[int]
) -> bool:
    """Return True if there exists an addition/neutral record whose anchor == li and maps to rj."""
    if li is None or rj is None:
        return False
    out1 = block.get("output_1") or []
    if not (0 <= li < len(out1)):
        return False
    for rec in block.get("nli_results") or []:
        lab = str(rec.get("label") or "").lower()
        if lab not in ("addition", "neutral"):
            continue
        anc = _anchor_as_int(rec.get("anchor"))
        if anc is None or anc != li:
            continue
        li2, rj2 = _map_record_indices(block, rec)
        if rj2 == rj:
            return True
    return False


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

    # severity order (for LEFT color only we will ignore 'addition'/'neutral')
    sev = {"contradiction": 3, "addition": 2, "neutral": 2, "entailment": 1}

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
        # Update LEFT color only by non-addition labels
        if lbl in ("contradiction", "entailment", "equivalent"):
            cur = left_color.get(i_left)
            norm_lbl = "entailment" if lbl == "equivalent" else lbl
            if cur is None or sev.get(norm_lbl, 0) > sev.get(cur, 0):
                left_color[i_left] = norm_lbl

    # Synthesize links for additions pointing to a LEFT anchor (so right addition spans have a mate)
    out1 = block.get("output_1") or []
    out2 = block.get("output_2") or []
    idx2 = _index_claims(out2)
    idx2_norm = {_norm(_get_claim_text(c)): j for j, c in enumerate(out2 or [])}
    for r in block.get("nli_results") or []:
        lab = str(r.get("label") or "").lower()
        if lab not in ("neutral", "addition"):
            continue
        anc = _anchor_as_int(r.get("anchor"))
        if anc is None or not (0 <= anc < len(out1)):
            continue
        prem = str(r.get("premise_raw") or r.get("premise") or "")
        hyp = str(r.get("hypothesis_raw") or r.get("hypothesis") or "")
        rj = idx2.get(hyp)
        if rj is None:
            rj = idx2.get(prem)
        if rj is None:
            # last try: normalized lookup
            cand = hyp or prem
            rj = idx2_norm.get(_norm(cand))
        if rj is None:
            continue
        # avoid duplicates
        lst = out_links.setdefault(anc, [])
        if (rj, "addition") not in lst:
            lst.append((rj, "addition"))

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
    html_parts = [
        '<div class="viewer-wrap"><div class="left-pane">',
        '<div class="left-title">Source text of Document A</div>',
    ]

    for pi, b in enumerate(blocks):
        out1 = b.get("output_1") or []
        out2 = b.get("output_2") or []
        links, left_color = _link_map_for_pair(b)
        # Build anchor maps (so additions snap to anchors)
        (
            left_add_anchor,
            right_add_to_left_anchor,
            right_add_to_right_anchor,
            _right_text_to_left_anchor,
            left_anchor_to_right_anchor,
            left_add_to_right_add,
        ) = _build_addition_anchors(b)
        # We also need "where does a LEFT anchor point on the RIGHT?" → use entailment map
        ent_L_to_R, _ent_R_to_L = _entailment_maps(b)

        # A left claim is an "orphan addition" if it has NO links at all (no contra/ent/neutral)
        # and we do not already have an addition anchor for it. Anchor it to the last sentence before it.
        fallback_left_add_anchor: Dict[int, int] = {}
        if out1:
            for i in range(len(out1)):
                raw_i = _get_claim_text(out1[i], strip=True)
                if not raw_i:
                    continue
                # already anchored as addition
                if i in (left_add_anchor or {}):
                    continue
                # any existing links → not an orphan
                if links.get(i):
                    continue
                # first sentence has no "previous" to anchor to; skip it
                if i == 0:
                    continue
                # Anchor to immediately previous left sentence
                fallback_left_add_anchor[i] = i - 1

        if fallback_left_add_anchor:
            left_add_anchor.update(fallback_left_add_anchor)
            for li_add, li_anchor in fallback_left_add_anchor.items():
                if li_anchor not in (left_anchor_to_right_anchor or {}):
                    rj_anchor, lbl_anchor = _best_right_for_left_anchor(b, li_anchor)
                    left_anchor_to_right_anchor[li_anchor] = (rj_anchor, lbl_anchor)

        # Build a set of left indices that serve as anchors for additions (neutral)
        anchor_left_idxs = set()
        idx1 = _index_claims(out1)
        _ = _index_claims(b.get("output_2") or [])
        for rr in b.get("nli_results") or []:
            lblr = str(rr.get("label") or "").lower()
            if lblr in ("neutral", "addition"):
                prem = str(rr.get("premise_raw") or rr.get("premise") or "")
                _ = str(rr.get("hypothesis_raw") or rr.get("hypothesis") or "")
                i_li = idx1.get(prem)
                # Prefer an explicit anchor index if your LLM provided one
                anc_idx = rr.get("anchor")
                if isinstance(anc_idx, int) and 0 <= anc_idx < len(out1):
                    i_li = anc_idx
                if i_li is not None:
                    anchor_left_idxs.add(i_li)

        if out1:
            # severity order
            sev_rank = {"contradiction": 3, "neutral": 2, "entailment": 1}

            spans = []
            for i1, c in enumerate(out1):
                raw = _get_claim_text(c)

                # choose best right idx by severity for this left i1 (if any)
                best_r = None
                best_lbl = ""
                for rj, lbl in links.get(i1, []):
                    if best_r is None or sev_rank.get(lbl, 0) > sev_rank.get(
                        best_lbl, 0
                    ):
                        best_r = rj
                        best_lbl = lbl or ""
                if best_lbl == "equivalent":
                    best_lbl = "entailment"

                # NLI color for the left span (worst label among its links)
                worst_lbl = (left_color.get(i1, "") or "").lower()
                self_col = _hover_color(worst_lbl)

                # Decide if THIS left span is an addition and compute anchors
                is_add = i1 in left_add_anchor
                cls = "hl addition" if is_add else ("hl " + worst_lbl)
                if is_add:
                    self_col = _hover_color("addition")
                anc_li = left_add_anchor.get(i1)
                # mark self-anchored (LLM anchored to itself)
                is_self_anchor = is_add and (anc_li == i1)
                # Display-anchor:
                #   - if this is the *first* sentence and self-anchored → show the NEXT sentence (original UX)
                #   - otherwise keep the real anchor (stable)
                disp_anc_li = anc_li
                if is_self_anchor and i1 == 0 and len(out1) > 1:
                    disp_anc_li = 1

                # RIGHT anchor for brackets (contra>ent) derived from the (display) left anchor itself
                anc_rj, anc_lbl = None, ""
                use_lbl_for = disp_anc_li if disp_anc_li is not None else anc_li
                if (use_lbl_for is not None) and (
                    use_lbl_for in left_anchor_to_right_anchor
                ):
                    anc_rj, anc_lbl = left_anchor_to_right_anchor[use_lbl_for]
                elif use_lbl_for is not None:
                    # compute on the fly
                    anc_rj, anc_lbl = _best_right_for_left_anchor(b, use_lbl_for)

                # Cross-doc mate target:
                # - for additions → **prefer the TRUE right addition mate** when known
                #   (this is what we want highlighted & bracketed),
                #   otherwise fall back to the anchor's contra/ent mate.
                # - for non-additions → best_r as before.
                j_add_for_left = left_add_to_right_add.get(i1) if is_add else None
                if is_add:
                    # Always target the RIGHT **anchor** (contra > ent) so the right pane highlights green/red.
                    if anc_rj is not None:
                        target_attr = f' data-target="R-{pi}-{anc_rj}"'
                        hcolor_attr = (
                            f' data-hcolor="{_hover_color(anc_lbl or "entailment")}"'
                        )
                    elif j_add_for_left is not None:
                        # Fallback only if no right anchor was found
                        target_attr = f' data-target="R-{pi}-{j_add_for_left}"'
                        hcolor_attr = (
                            f' data-hcolor="{_hover_color(anc_lbl or "entailment")}"'
                        )
                    else:
                        target_attr = ""
                        hcolor_attr = ""
                else:
                    target_attr = (
                        f' data-target="R-{pi}-{best_r}"' if best_r is not None else ""
                    )
                    hcolor_attr = (
                        f' data-hcolor="{_hover_color(best_lbl)}"'
                        if best_r is not None
                        else ""
                    )

                # Addition tagging + intra-doc anchors (left + right) for JS
                extras = []
                if is_add:
                    extras.append('data-kind="addition"')
                    # lanchor brackets show NEIGHBOR if self-anchored
                    if disp_anc_li is not None:
                        extras.append(f'data-lanchor="L-{pi}-{disp_anc_li}"')
                    if is_self_anchor:
                        extras.append('data-selfanchor="1"')
                    # Bracket the RIGHT **in-pane anchor** (counterpart of the left anchor).
                    if anc_rj is not None:
                        extras.append(f'data-ranchor="R-{pi}-{anc_rj}"')
                    # (Optional) expose the right addition mate for tooling/QA; JS ignores it today.
                    if j_add_for_left is not None:
                        extras.append(f'data-rmate="R-{pi}-{j_add_for_left}"')

                extra_attr = (" " + " ".join(extras)) if extras else ""

                # NOW do term highlighting (we finally know is_add & j_add_for_left)
                if focus and focus[0] == pi and focus[1] == i1 and contra_terms:
                    orient = (contra_terms or {}).get("_orientation", "")
                    # Choose the SAME counterpart we used to compute the delta,
                    # so the diff mask doesn't filter everything out.
                    mate_txt = None
                    if is_add:
                        if (
                            orient == "anchor-vs-left"
                            and anc_li is not None
                            and 0 <= anc_li < len(out1)
                        ):
                            # delta was computed: anchor (span_1) vs LEFT addition (span_2)
                            # -> build mask against the LEFT anchor text
                            mate_txt = _get_claim_text(out1[anc_li])
                        elif j_add_for_left is not None and 0 <= j_add_for_left < len(
                            out2
                        ):
                            # delta was computed: LEFT addition (span_1) vs RIGHT mate (span_2)
                            mate_txt = _get_claim_text(out2[j_add_for_left])
                        elif best_r is not None and 0 <= best_r < len(out2):
                            # fallback: best right if nothing else
                            mate_txt = _get_claim_text(out2[best_r])
                    else:
                        if best_r is not None and 0 <= best_r < len(out2):
                            mate_txt = _get_claim_text(out2[best_r])

                    mask = (
                        _compute_diff_mask(raw, mate_txt)
                        if mate_txt is not None
                        else None
                    )

                    # Which terms to paint on the LEFT:
                    # - anchor-vs-left -> new stuff is in span_2 (the LEFT addition)
                    # - left-vs-right  -> new stuff for LEFT is span_1
                    if is_add and orient == "anchor-vs-left":
                        yterms = (contra_terms or {}).get("from_span_2") or []
                    else:
                        yterms = (contra_terms or {}).get("from_span_1") or []

                    txt = _wrap_terms_html(raw, yterms, mask)
                else:
                    txt = _escape(raw)

                # Make the focused left span look selected right after re-render
                if focus and focus[0] == pi and focus[1] == i1:
                    cls = cls + " selected"

                # If THIS is the focused left ADDITION and we do have delta/contra terms,
                # paint the body as "entailment-feel" green so yellow tokens pop clearly.
                if (
                    is_add
                    and focus
                    and focus[0] == pi
                    and focus[1] == i1
                    and contra_terms
                ):
                    cls = cls + " as-entailment"

                spans.append(
                    f'<span id="L-{pi}-{i1}" class="{cls}" data-pair="{pi}" data-left="{i1}" data-selfcolor="{self_col}"{target_attr}{hcolor_attr}{extra_attr}>{txt}</span>'
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


REASON_BY_LABEL = NLI_REASON_BY_LABEL


def _hover_color(lbl: str) -> str:
    return HOVER_PALETTE.get((lbl or "").lower(), HOVER_PALETTE["neutral"])


def _embed_right_claims_in_paragraph(
    par_text: str,
    out2: List[Dict[str, Any]],
    out1: List[Dict[str, Any]],
    k: int,
    label_for_right: Dict[int, str],
    best_for_right: Dict[int, Tuple[int, str]],
    target_right_idx: Optional[int],
    contra_terms: Optional[Dict[str, List[str]]],
    anchor_idx_for_right: Optional[Dict[int, int]] = None,
    anchor_text_for_right: Optional[Dict[int, str]] = None,
    fallback_left_anchor_by_text: Optional[Dict[str, int]] = None,
    left_anchor_to_right_anchor: Optional[Dict[int, Tuple[Optional[int], str]]] = None,
    left_add_to_right_add: Optional[Dict[int, int]] = None,
    ent_right_to_left: Optional[Dict[int, int]] = None,
) -> str:
    """
    Return the FULL Document B paragraph with all right-claims embedded in-place
    (preserving original order/positions). Each embedded claim keeps the same
    id/data-* attributes as when rendered as a separate list, so hover/click
    linking works the same way.
    """
    if not par_text:
        return "—"

    # Build alternation over all claim texts, longest-first to avoid partial overlaps.
    claims: List[Tuple[int, str]] = []
    for j, c in enumerate(out2 or []):
        raw = _get_claim_text(c, strip=True)
        if raw:
            claims.append((j, raw))
    if not claims:
        return _escape(par_text)
    claims.sort(key=lambda t: len(t[1]), reverse=True)

    # Named groups, one per claim index.
    parts = [f"(?P<G{j}>{re.escape(txt)})" for j, txt in claims]
    rx = re.compile("|".join(parts), flags=re.IGNORECASE | re.UNICODE)

    used: set[int] = set()  # wrap each claim only once
    out: List[str] = []
    last = 0
    # quick index for right claims by text (case-sensitive trimmed)
    idx2: Dict[str, int] = {}
    for j, t in claims:
        idx2[t] = j

    for m in rx.finditer(par_text):
        s, e = m.span()
        if s > last:
            out.append(_escape(par_text[last:s]))

        # Which group matched?
        j_hit: Optional[int] = None
        for j, _txt in claims:
            if m.groupdict().get(f"G{j}") is not None:
                j_hit = j
                break
        seg = m.group(0)

        if j_hit is not None:
            # label + best mate on the left (to keep cross-hover/selection)
            lbl = (label_for_right.get(j_hit, "") or "").lower()
            if lbl == "equivalent":
                lbl = "entailment"
            # include 'addition' so blue styling applies on the right too
            cls = "hl " + (
                lbl
                if lbl in ("contradiction", "neutral", "addition", "entailment")
                else ""
            )
            # If we are showing delta terms for an ADDITION, lightly wash the right span green too
            is_add = lbl in ("addition", "neutral")
            if (
                is_add
                and contra_terms
                and (target_right_idx is not None)
                and (j_hit == int(target_right_idx))
            ):
                cls = cls + " as-entailment"

            self_col = _hover_color(lbl or "neutral")

            li_for_j = best_for_right.get(j_hit)
            if li_for_j:
                li_idx, lbl_for_j = li_for_j
                target_attr = f' data-target="L-{k}-{li_idx}"'
                hcolor_attr = f' data-hcolor="{_hover_color(lbl_for_j)}"'
            else:
                target_attr = ""
                hcolor_attr = f' data-hcolor="{_hover_color(lbl or "neutral")}"'

            # FINAL SAFETY NET: if still no cross-doc target, use entailment map R->L
            if not target_attr and ent_right_to_left and (j_hit in ent_right_to_left):
                li_idx = ent_right_to_left[j_hit]
                target_attr = f' data-target="L-{k}-{li_idx}"'
                # color: default to entailment green for anchors discovered via entailment
                hcolor_attr = f' data-hcolor="{_hover_color("entailment")}"'

            # Addition wiring: point to *left* anchor if provided; attach *right* in-pane anchor id.
            extras = []
            is_add = lbl in ("neutral", "addition")
            # If we have no model label but can infer via text→anchor mapping → treat as addition
            left_anchor_idx_fallback: Optional[int] = None
            if not is_add and fallback_left_anchor_by_text:
                left_anchor_idx_fallback = fallback_left_anchor_by_text.get(_norm(seg))
                if left_anchor_idx_fallback is not None:
                    is_add = True
                    lbl = "addition"
                    cls = "hl addition"
                    self_col = _hover_color("addition")
            if is_add:
                extras.append('data-kind="addition"')
                # left anchor (cross-doc): if known, point to it and store for JS highlight
                if anchor_idx_for_right and j_hit in anchor_idx_for_right:
                    const_li_anchor = anchor_idx_for_right[j_hit]
                    target_attr = f' data-target="L-{k}-{const_li_anchor}"'
                    # bracket color comes from the anchor's own best link (contra > ent). Fall back to green.
                    anc_col_lbl = "entailment"
                    if (
                        left_anchor_to_right_anchor
                        and const_li_anchor in left_anchor_to_right_anchor
                    ):
                        _rj_anchor, _lbl = left_anchor_to_right_anchor[const_li_anchor]
                        if _lbl in ("contradiction", "entailment"):
                            anc_col_lbl = _lbl
                    hcolor_attr = f' data-hcolor="{_hover_color(anc_col_lbl)}"'
                    extras.append(f'data-lanchor="L-{k}-{const_li_anchor}"')
                elif left_anchor_idx_fallback is not None:
                    target_attr = f' data-target="L-{k}-{left_anchor_idx_fallback}"'
                    anc_col_lbl = "entailment"
                    if (
                        left_anchor_to_right_anchor
                        and left_anchor_idx_fallback in left_anchor_to_right_anchor
                    ):
                        _rj_anchor, _lbl = left_anchor_to_right_anchor[
                            left_anchor_idx_fallback
                        ]
                        if _lbl in ("contradiction", "entailment"):
                            anc_col_lbl = _lbl
                    hcolor_attr = f' data-hcolor="{_hover_color(anc_col_lbl)}"'
                    extras.append(f'data-lanchor="L-{k}-{left_anchor_idx_fallback}"')
                # Right in-pane anchor (same text claim on B)
                if anchor_text_for_right and j_hit in anchor_text_for_right:
                    anc_txt = anchor_text_for_right[j_hit]
                    r_anchor = idx2.get(anc_txt)
                    if r_anchor is not None and r_anchor != j_hit:
                        extras.append(f'data-ranchor="R-{k}-{r_anchor}"')
                # True self-anchored RIGHT: left_add_to_right_add[la] == j_hit
                if (
                    is_add
                    and anchor_idx_for_right
                    and j_hit in anchor_idx_for_right
                    and left_add_to_right_add
                ):
                    la = anchor_idx_for_right[j_hit]
                    if left_add_to_right_add.get(la) == j_hit:
                        extras.append('data-selfanchor="1"')
                # expose the *left addition mate* for this right addition (if any)
                if left_add_to_right_add:
                    for li_add, rj_add in left_add_to_right_add.items():
                        if int(rj_add) == int(j_hit):
                            extras.append(f'data-lmate="L-{k}-{li_add}"')
                            break
            kind_attr = (" " + " ".join(extras)) if extras else ""

            # If this is the specific right claim we're focusing on, inject contradicting terms
            if (
                (target_right_idx is not None)
                and (j_hit == int(target_right_idx))
                and contra_terms
            ):
                # find the most sensible left counterpart for this right span
                li_for_terms = None
                if best_for_right.get(j_hit):
                    li_for_terms = best_for_right[j_hit][0]
                elif ent_right_to_left and j_hit in ent_right_to_left:
                    li_for_terms = ent_right_to_left[j_hit]
                elif anchor_idx_for_right and j_hit in anchor_idx_for_right:
                    li_for_terms = anchor_idx_for_right[j_hit]
                left_seg = None
                if li_for_terms is not None and 0 <= li_for_terms < len(out1):
                    left_seg = _get_claim_text(out1[li_for_terms])
                mask = (
                    _compute_diff_mask(seg, left_seg) if left_seg is not None else None
                )
                inner = _wrap_terms_html(
                    seg, (contra_terms or {}).get("from_span_2") or [], mask
                )
            else:
                inner = _escape(seg)

            # Persist selection through re-render if this is the target right span
            if target_right_idx is not None and j_hit == int(target_right_idx):
                cls = cls + " selected"

            # Only wrap the first occurrence of each claim to avoid duplicates
            if j_hit in used:
                out.append(_escape(seg))
            else:
                out.append(
                    f'<span id="R-{k}-{j_hit}" class="{cls}" data-pair="{k}" data-right="{j_hit}" data-selfcolor="{self_col}"{target_attr}{hcolor_attr}{kind_attr}>{inner}</span>'
                )
                used.add(j_hit)
        else:
            out.append(_escape(seg))
        last = e
    if last < len(par_text):
        out.append(_escape(par_text[last:]))
    return "".join(out)


def _render_right_col(
    blocks: List[Dict[str, Any]],
    focus: Tuple[int, Optional[int]],
    contra_terms: Optional[Dict[str, List[str]]] = None,
    target_right_idx: Optional[int] = None,
) -> str:
    """
    Static right column (independent scroller).
    - Always shows the FULL paragraph of Document B for the selected pair.
    - Shows ALL extracted claims for B (not only the matched span).
    - If a left span is selected and contra_terms are available, highlights those terms
      inside the full paragraph (and also in the specific right span if target_right_idx).
    """
    if not blocks:
        return (
            '<div class="right-pane-inner">'
            '<div class="right-title">Snippet of text in Document B</div>'
            '<div class="mirror-box">—</div>'
            "</div>"
        )

    k, i_left = focus
    k = max(0, min(k, len(blocks) - 1))
    b = blocks[k]

    out2 = b.get("output_2") or []
    links, _left_color = _link_map_for_pair(b)

    # Decide label per right-claim (worst wins), but we will render ALL claims
    severity = NLI_SEVERITY
    label_for_right: Dict[int, str] = {}

    def take_worst(cur: str, new: str) -> str:
        return new if severity.get(new, 0) > severity.get(cur or "", 0) else cur

    # Accumulate labels from links (if a left is selected, keep those; otherwise aggregate all)
    if i_left is None:
        for li, pairs in links.items():
            for rj, lbl in pairs:
                lbl = (str(lbl) or "").lower()
                if lbl == "equivalent":
                    lbl = "entailment"
                label_for_right[rj] = take_worst(
                    label_for_right.get(rj, ""), str(lbl).lower()
                )
    else:
        for rj, lbl in links.get(i_left, []):
            label_for_right[rj] = take_worst(
                label_for_right.get(rj, ""), str(lbl).lower()
            )

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

    # FULL paragraph of Document B with right-claims embedded in-place (preserve order)
    paragraph_b = _text_right(b)
    # Build addition anchors so right additions can carry both left & right anchors
    (
        left_add_anchor,
        right_add_to_left_anchor,
        right_add_to_right_anchor,
        right_text_to_left_anchor,
        left_anchor_to_right_anchor,
        left_add_to_right_add,
    ) = _build_addition_anchors(b)

    # Ensure the right-side **anchor** (contra > ent) shows green/red background,
    # but do NOT accidentally promote a *right addition* to green.
    right_add_idxs = set((right_add_to_left_anchor or {}).keys())
    for li_anchor, (aj, anc_lbl) in (left_anchor_to_right_anchor or {}).items():
        if aj is None or not (0 <= aj < len(out2)):
            continue
        # If this right index is an addition, keep it blue.
        if aj in right_add_idxs:
            continue
        label_for_right[aj] = anc_lbl or "entailment"
        best_for_right[aj] = (li_anchor, anc_lbl or "entailment")

    # Promote the *real* right anchors (green/red) BUT do not accidentally recolor any right ADDITIONS.
    if right_add_to_right_anchor and right_add_to_left_anchor:
        right_add_idxs = set((right_add_to_left_anchor or {}).keys())
        for r_add, r_anchor in (right_add_to_right_anchor or {}).items():
            # skip: invalid anchor, self-anchored right, or if the anchor itself is an addition
            if r_anchor is None or not (0 <= r_anchor < len(out2)):
                continue
            if r_anchor == r_add:
                continue
            if r_anchor in right_add_idxs:
                continue
            li_anchor = (right_add_to_left_anchor or {}).get(r_add)
            if li_anchor is None:
                continue
            # color the *anchor* green/red (contra > ent)
            anc_lbl = "entailment"
            if left_anchor_to_right_anchor and li_anchor in left_anchor_to_right_anchor:
                _rjA, _lblA = left_anchor_to_right_anchor[li_anchor]
                if _lblA in ("contradiction", "entailment"):
                    anc_lbl = _lblA
            label_for_right[r_anchor] = anc_lbl
            best_for_right[r_anchor] = (li_anchor, anc_lbl)
    # For the embedder, pass:
    #   - left anchor indices for cross-doc target + data-lanchor
    #   - the exact right anchor TEXT (so it can locate the right in-pane anchor by text)
    anchor_text_for_right: Dict[int, str] = {}
    out1 = b.get("output_1") or []
    out2 = b.get("output_2") or []
    # Prefer *right* anchor when we have one (closest green in B); else fall back to the entailing mate of the left anchor
    for rj, anc_rj in (right_add_to_right_anchor or {}).items():
        if 0 <= anc_rj < len(out2):
            anchor_text_for_right[rj] = _get_claim_text(out2[anc_rj])
    if anchor_text_for_right:
        pass
    # Fill remaining with entailing right of the left anchor (if any)
    ent_L_to_R, ent_R_to_L = _entailment_maps(b)
    for rj, li_anchor in (right_add_to_left_anchor or {}).items():
        if rj in anchor_text_for_right:
            continue
        if li_anchor in ent_L_to_R:
            aj = ent_L_to_R[li_anchor]
            if 0 <= aj < len(out2):
                anchor_text_for_right[rj] = _get_claim_text(out2[aj])

    # If the selected LEFT is an ADDITION, we may be using the "display anchor" (next sentence for self-anchored first).
    # Promote that right mate as well, so its class is green/red (not blue).
    if i_left is not None:
        try:
            out1_local = b.get("output_1") or []
            (
                left_add_anchor,
                right_add_to_left_anchor_local,
                right_add_to_right_anchor_local,
                _right_text_to_left_anchor,
                left_anchor_to_right_anchor_local,
                _left_add_to_right_add_local,
            ) = _build_addition_anchors(b)
            if i_left in (left_add_anchor or {}):
                li_anchor_real = left_add_anchor[i_left]
                # mirror left-pane logic: if self-anchored & first -> display next sentence as anchor
                disp_anc_li = li_anchor_real
                if li_anchor_real == i_left and i_left == 0 and len(out1_local) > 1:
                    disp_anc_li = 1
                # find right mate of the display anchor for coloring
                if disp_anc_li is not None:
                    aj_disp, lbl_disp = _best_right_for_left_anchor(b, disp_anc_li)
                    if aj_disp is not None and 0 <= aj_disp < len(out2):
                        label_for_right[aj_disp] = lbl_disp or "entailment"
                        best_for_right[aj_disp] = (
                            disp_anc_li,
                            (lbl_disp or "entailment"),
                        )
        except Exception:
            pass

    # Decide which right span should be "pre-selected":
    # - if the selected left is an ADDITION, prefer the *actual right addition mate*;
    #   if missing, fall back to the anchor's contra/ent mate.
    selected_rj = target_right_idx
    # If caller provided an explicit target_right_idx (e.g., left-click computed rj),
    # do NOT override it here. Only compute when it's missing.
    if i_left is not None and selected_rj is None:
        try:
            # Build anchors to find left→right anchor mapping
            if i_left in (left_add_anchor or {}):
                li_anchor = left_add_anchor[i_left]
                # 1) try the true right addition mate
                rj_add = left_add_to_right_add.get(i_left)
                if rj_add is not None:
                    selected_rj = rj_add
                    # keep a stable label for visibility
                    if not label_for_right.get(rj_add):
                        label_for_right[rj_add] = "addition"
                    best_for_right[rj_add] = (li_anchor, "addition")
                else:
                    # 2) fallback to the anchor's contra/ent mate
                    maybe_rj, anc_lbl = (left_anchor_to_right_anchor or {}).get(
                        li_anchor, (None, "")
                    )
                    if maybe_rj is not None:
                        selected_rj = maybe_rj
                        if not label_for_right.get(maybe_rj):
                            label_for_right[maybe_rj] = anc_lbl or "entailment"
                        best_for_right[maybe_rj] = (li_anchor, anc_lbl or "entailment")
        except Exception:
            pass

    claims_body = _embed_right_claims_in_paragraph(
        paragraph_b,
        out2,
        out1,
        k,
        label_for_right,
        best_for_right,
        selected_rj,
        (contra_terms or {}),
        anchor_idx_for_right=right_add_to_left_anchor,  # for data-lanchor + cross-doc target
        anchor_text_for_right=anchor_text_for_right,  # for data-ranchor (in-pane)
        fallback_left_anchor_by_text=right_text_to_left_anchor,  # anchor by text if no rj
        left_anchor_to_right_anchor=left_anchor_to_right_anchor,  # color brackets by contra/ent
        left_add_to_right_add=left_add_to_right_add,  # mark true self-anchors
        ent_right_to_left=ent_R_to_L,  # ensure every right span can target some left
    )

    hdr = f"Document B — claims (pair {k+1})"

    return f"""
      <div class="right-pane-inner">
        <div class="right-title">Snippet of text in Document B</div>
        <div class="mirror-box" data-idx="{k}">
          <div class="para-head">{hdr}</div>
          <div class="para-inner">{claims_body}</div>
        </div>
      </div>
    """


def _render_reason(blocks, focus, target_right_idx: Optional[int] = None):
    k, i_left = focus
    if not blocks or k < 0 or k >= len(blocks) or i_left is None:
        # Right-only selection: resolve by right text.
        if blocks and 0 <= k < len(blocks) and target_right_idx is not None:
            b = blocks[k]
            out2 = b.get("output_2") or []
            if 0 <= int(target_right_idx) < len(out2):
                txtR = _get_claim_text(out2[int(target_right_idx)])
                for r in b.get("nli_results") or []:
                    lab = str(r.get("label") or "").lower()
                    prem = str(r.get("premise_raw") or r.get("premise") or "")
                    hyp = str(r.get("hypothesis_raw") or r.get("hypothesis") or "")
                    if txtR and (txtR == hyp or txtR == prem):
                        reason = (
                            r.get("explanation")
                            or r.get("reason")
                            or r.get("reasoning")
                            or REASON_BY_LABEL.get(lab, "")
                        )
                        return (
                            '<div class="reason-wrap"><div class="reason-title"><b>Explanation</b></div>'
                            f'<div class="reason-card">{html.escape(str(reason))}</div>'
                            "</div>"
                        )
                # Last resort for right-only selection
                return (
                    '<div class="reason-wrap"><div class="reason-title"><b>Explanation</b></div>'
                    f'<div class="reason-card">{html.escape(REASON_BY_LABEL.get("addition",""))}</div>'
                    "</div>"
                )
        return '<div class="reason-wrap"></div>'

    b = blocks[k]
    out1 = b.get("output_1") or []
    if not (0 <= i_left < len(out1)):
        return '<div class="reason-wrap"></div>'

    items: List[str] = []
    clicked_left_text = _get_claim_text(out1[i_left])

    # 1) Exact pair (i_left, target_right_idx) if provided.
    if target_right_idx is not None:
        for r in b.get("nli_results") or []:
            li, rj = _map_record_indices(b, r)
            if li == i_left and rj == target_right_idx:
                lab = str(r.get("label") or "").lower()
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
                    break
        # Fallback: right-text equality if indices didn’t line up
        if not items:
            out2 = b.get("output_2") or []
            if 0 <= int(target_right_idx) < len(out2):
                txtR = _get_claim_text(out2[int(target_right_idx)])
                for r in b.get("nli_results") or []:
                    lab = str(r.get("label") or "").lower()
                    prem = str(r.get("premise_raw") or r.get("premise") or "")
                    hyp = str(r.get("hypothesis_raw") or r.get("hypothesis") or "")
                    if txtR and (txtR == hyp or txtR == prem):
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
                            break

    # 2) If the clicked LEFT is an addition, prefer the addition record(s) anchored to its anchor,
    #    and pick the one whose text matches the clicked left text.
    if not items:
        try:
            left_add_anchor, *_ = _build_addition_anchors(b)
        except Exception:
            left_add_anchor = {}
        if i_left in (left_add_anchor or {}):
            anchor_li = left_add_anchor[i_left]
            candidates = []
            for r in b.get("nli_results") or []:
                lab = (r.get("label") or "").lower()
                anc = _anchor_as_int(r.get("anchor"))
                if lab in ("addition", "neutral") and anc == anchor_li:
                    candidates.append(r)
            if candidates:
                picked = None
                for r in candidates:
                    prem = str(r.get("premise_raw") or r.get("premise") or "")
                    hyp = str(r.get("hypothesis_raw") or r.get("hypothesis") or "")
                    if clicked_left_text and (
                        clicked_left_text == prem or clicked_left_text == hyp
                    ):
                        picked = r
                        break
                if picked is None and clicked_left_text:
                    ncl = _norm(clicked_left_text)
                    for r in candidates:
                        prem = str(r.get("premise_raw") or r.get("premise") or "")
                        hyp = str(r.get("hypothesis_raw") or r.get("hypothesis") or "")
                        if _norm(prem) == ncl or _norm(hyp) == ncl:
                            picked = r
                            break
                if picked is None:
                    picked = candidates[0]
                lab = (picked.get("label") or "").lower()
                reason = (
                    picked.get("explanation")
                    or picked.get("reason")
                    or picked.get("reasoning")
                    or REASON_BY_LABEL.get(lab, "")
                )
                if reason:
                    items.append(
                        f'<div class="reason-card">{html.escape(str(reason))}</div>'
                    )

    # 3) Any record whose ANCHOR equals this left index (covers self-anchored additions too).
    if not items:
        for r in b.get("nli_results") or []:
            lab = str(r.get("label") or "").lower()
            if _anchor_as_int(r.get("anchor")) != i_left:
                continue
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
                break

    # 4) Else: a record that maps by the left index (any label)
    if not items:
        for r in b.get("nli_results") or []:
            li, _rj = _map_record_indices(b, r)
            lab = str(r.get("label") or "").lower()
            if li != i_left:
                continue
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
                break

    # 5) If still nothing and the clicked LEFT span is an addition → generic addition reason.
    if not items and b.get("nli_results"):
        try:
            left_add_anchor, *_ = _build_addition_anchors(b)
            if i_left in (left_add_anchor or {}):
                items.append(
                    f'<div class="reason-card">{html.escape(REASON_BY_LABEL.get("addition",""))}</div>'
                )
        except Exception:
            pass

    # 6) Absolute last resort: worst label default copy.
    if not items:
        links, _ = _link_map_for_pair(b)
        sev = NLI_SEVERITY
        worst = ""
        for _rj, lbl in links.get(i_left, []):
            if sev.get(lbl, 0) > sev.get(worst, 0):
                worst = lbl
        if worst:
            items.append(
                f'<div class="reason-card">{html.escape(REASON_BY_LABEL.get(worst, ""))}</div>'
            )

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
    use_for_code: bool = False,
) -> Tuple[str, str]:
    """
    Returns (align_json_path, align_preview_json_str[:N]).
    """
    p1 = Path(doc1.name if hasattr(doc1, "name") else doc1)
    p2 = Path(doc2.name if hasattr(doc2, "name") else doc2)

    # Enforce document length restriction (≤ 5000 characters each)
    try:
        # paragraphs_a = separate_points(
        #     merge_incomplete_sentences(get_paragraphs_from_docx(p1))
        # )
        # paragraphs_b = separate_points(
        #     merge_incomplete_sentences(get_paragraphs_from_docx(p2))
        # )
        paragraphs_a = _read_paragraphs_generic(p1, is_code=bool(use_for_code))
        paragraphs_b = _read_paragraphs_generic(p2, is_code=bool(use_for_code))
    except Exception as e:
        # Surface a real error instead of continuing
        msg = f"Failed to read documents: {e}"
        raise gr.Error(msg)

    len_a = sum(map(len, paragraphs_a))
    len_b = sum(map(len, paragraphs_b))
    if len_a > 5000 or len_b > 5000:
        msg = f"Document too long: A={len_a} chars, B={len_b} chars. Limit is 5000. Processing stopped."
        gr.Warning(msg)
        raise gr.Error(msg)

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
    llm_model_id: Optional[str],
    use_for_code: bool,
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
        use_for_code=use_for_code,
    )

    if use_llm_12:
        # Choose prompt: code-specific vs normal
        effective_prompt = (
            (LLM_NLI_SYSTEM_PROMPT_CODE or claim_prompt)
            if use_for_code
            else claim_prompt
        )
        pairs_path = run_llm_nli_file(
            align_path,
            system_prompt=effective_prompt,
            model_name=llm_model_id or DEFAULT_MODEL,
        )
        pairs_path = str(pairs_path)  # ensure str for downstream File components
        pairs = json.loads(Path(pairs_path).read_text(encoding="utf-8"))
    else:
        # Stage 1
        claims_path = run_claim_extraction(align_path, system_prompt=claim_prompt)
        # Stage 2 (nli_predict.run_nli_file accepts (model_name, file_obj-or-path))

        nli_out_path = run_nli_file(
            nli_model_name or (MODELS_LIST[0] if MODELS_LIST else None),
            str(claims_path),
        )
        pairs_path = str(nli_out_path)  # normalize to str
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


def _bridge_combo(ps, v, use_llm_contra=False, contra_model_id=DEFAULT_MODEL):
    k, l_ = 0, None
    try:
        if v and v.startswith("P:"):
            k = int(v.split(":", 1)[1])
            return (
                _render_left(ps or []),
                _render_right_col(ps or [], (k, None)),
                _render_reason(ps or [], (k, None)),
                gr.update(value=str(k + 1)) if (ps and len(ps) > 0) else gr.update(),
            )
        if v and v.startswith("S:"):
            _t, a, b = v.split(":")
            k, l_ = int(a), int(b)
            info = _get_precomputed_contra(ps or [], k, l_)
            terms = None
            rj = None
            if not info:
                # Only compute terms if there is a contradiction for this focus.
                info = _compute_contra_terms_for_focus(
                    ps or [],
                    (k, l_),
                    bool(use_llm_contra),
                    contra_model_id or DEFAULT_MODEL,
                )
                if info:
                    # store back into cache so subsequent clicks are instant & stable
                    block = (ps or [])[k]
                    cache = block.get("_contra_cache") or {}
                    cache[l_] = info
                    block["_contra_cache"] = cache
            if info:
                # Only contradictions reach here
                terms = info["terms"]
                rj = info.get(
                    "right_idx"
                )  # << ensure the RIGHT gets selected & highlighted

            # ADDITION (blue) on LEFT-CLICK → compute DELTA terms as well (not only self-anchored)
            # Strategy:
            #   1) If clicked left span is an addition, prefer its true right addition mate.
            #   2) If no direct mate, use the anchor's contra/ent mate as a fallback for bracket color + delta.
            try:
                if terms is None:  # don't overwrite contradiction terms if already set
                    block = (ps or [])[k]
                    (
                        left_add_anchor,
                        _r2l,
                        _r2r,
                        _txt2l,
                        left_anchor_to_right_anchor,
                        left_add_to_right_add,
                    ) = _build_addition_anchors(block)
                    if l_ in (left_add_anchor or {}):
                        li_anchor = left_add_anchor.get(l_)
                        out1 = block.get("output_1") or []
                        out2 = block.get("output_2") or []
                        # Resolve right addition and right anchor
                        rj_add = left_add_to_right_add.get(l_)
                        rj_anchor, _lbl_anchor = (
                            left_anchor_to_right_anchor or {}
                        ).get(li_anchor, (None, ""))
                        # Compute delta terms vs the TRUE right addition mate when possible
                        if (
                            rj_add is not None
                            and 0 <= l_ < len(out1)
                            and 0 <= rj_add < len(out2)
                        ):
                            left_text = _get_claim_text(out1[l_])
                            right_text = _get_claim_text(out2[rj_add])
                            terms = _get_delta_terms(
                                left_text,
                                right_text,
                                bool(use_llm_contra),
                                contra_model_id or DEFAULT_MODEL,
                            )
                            # orientation: LEFT vs RIGHT addition
                            if isinstance(terms, dict):
                                terms["_orientation"] = "left-vs-right"
                            # UI selection: prefer the RIGHT **anchor**; fall back to the addition if no anchor
                            rj = rj_anchor if (rj_anchor is not None) else rj_add
                        elif (
                            (li_anchor is not None)
                            and 0 <= l_ < len(out1)
                            and 0 <= li_anchor < len(out1)
                        ):
                            # 3) LAST RESORT: compute delta vs LEFT ANCHOR (right mate unknown)
                            anchor_text = _get_claim_text(out1[li_anchor])
                            addition_text = _get_claim_text(out1[l_])
                            if anchor_text and addition_text:
                                terms = _get_delta_terms(
                                    anchor_text,
                                    addition_text,
                                    bool(use_llm_contra),
                                    contra_model_id or DEFAULT_MODEL,
                                )
                                # orientation: ANCHOR vs LEFT addition
                                if isinstance(terms, dict):
                                    terms["_orientation"] = "anchor-vs-left"
                                # No right selection if we don't know the right anchor yet
                                rj = rj_anchor
                    else:
                        # Fallback: if we failed to recover addition anchors (edge cases),
                        # do an immediate neighbor-based anchor so delta still shows on first click.
                        out1 = block.get("output_1") or []
                        if 0 <= l_ < len(out1):
                            # neighbor rule: if first → next, else previous
                            alt_anchor = (
                                1
                                if (l_ == 0 and len(out1) > 1)
                                else (l_ - 1 if l_ > 0 else None)
                            )
                            if alt_anchor is not None and 0 <= alt_anchor < len(out1):
                                terms = _get_delta_terms(
                                    _get_claim_text(out1[alt_anchor]),
                                    _get_claim_text(out1[l_]),
                                    bool(use_llm_contra),
                                    contra_model_id or DEFAULT_MODEL,
                                )
                                if isinstance(terms, dict):
                                    terms["_orientation"] = "anchor-vs-left"
                                rj = None
            except Exception:
                # fail-safe: ignore delta on error; UI will still bracket anchors
                pass

            # Note: for additions/neutral/entailment → terms=None.
            # _render_right_col will still preselect the right anchor (contra>ent) if this left is an addition,
            # and no contra phrases will be highlighted.
            return (
                _render_left(ps or [], (k, l_), terms),
                _render_right_col(ps or [], (k, l_), terms, rj),
                _render_reason(ps or [], (k, l_), rj),
                gr.update(),  # DO NOT update Radio from span clicks -> prevents second overwrite render
            )
        if v and v.startswith("R:"):
            # Click from RIGHT span -> we compute terms for the specific (k, rj)
            # and choose the "best" left mate for that right span to keep both panes in sync.
            _t, a, b = v.split(":")
            k, rj = int(a), int(b)
            block = (ps or [])[k]
            out1 = block.get("output_1") or []
            out2 = block.get("output_2") or []
            links, _ = _link_map_for_pair(block)
            severity = NLI_SEVERITY
            best_li, best_lbl = None, ""
            for li, pairs in links.items():
                for r_idx, lbl in pairs:
                    if r_idx == rj:
                        if best_li is None or severity.get(lbl, 0) > severity.get(
                            best_lbl, 0
                        ):
                            best_li, best_lbl = li, lbl
            if (
                best_li is None
                or not (0 <= best_li < len(out1))
                or not (0 <= rj < len(out2))
            ):
                # Extra fallback: use synthesized anchors for right additions
                try:
                    _la, _r2l, _r2r, _txt2l = _build_addition_anchors(block)
                    if rj in _r2l:
                        best_li = _r2l[rj]
                except Exception:
                    best_li = None
                if best_li is None or not (0 <= best_li < len(out1)):
                    # last resort: just show the paragraph
                    return (
                        _render_left(ps or []),
                        _render_right_col(ps or [], (k, None)),
                        _render_reason(ps or [], (k, None)),
                        gr.update(value=str(k + 1)),
                    )
            # Only compute contradiction terms when the best link label is 'contradiction'
            terms = None
            if (best_lbl or "").lower() == "contradiction":
                left_text = _get_claim_text(out1[best_li])
                right_text = _get_claim_text(out2[rj])
                terms = _get_contra_terms(
                    left_text,
                    right_text,
                    bool(use_llm_contra),
                    contra_model_id or DEFAULT_MODEL,
                )
            else:
                # ADDITION: compute DELTA terms ONLY when this right span is the true mate of a LEFT addition.
                # (Do NOT compute for right-only additions without a left addition partner.)
                try:
                    _la, r2l, _r2r, _txt2l, _la2ra, _ladd2radd = (
                        _build_addition_anchors(block)
                    )
                    # try to bind left partner for this right
                    if best_li is None and rj in (r2l or {}):
                        best_li = r2l[rj]
                    has_true_pair = (best_li is not None) and (
                        _ladd2radd.get(best_li) == rj
                    )
                    if has_true_pair:
                        left_text = _get_claim_text(out1[best_li])
                        right_text = _get_claim_text(out2[rj])
                        if left_text and right_text:
                            terms = _get_delta_terms(
                                left_text,
                                right_text,
                                bool(use_llm_contra),
                                contra_model_id or DEFAULT_MODEL,
                            )
                except Exception:
                    pass
            return (
                _render_left(ps or [], (k, best_li), terms),
                _render_right_col(ps or [], (k, best_li), terms, target_right_idx=rj),
                _render_reason(ps or [], (k, best_li), rj),
                gr.update(),  # DO NOT update Radio from span clicks -> prevents second overwrite render
            )
    except Exception:
        pass
    return (
        _render_left(ps or []),
        _render_right_col(ps or [], (k, l_)),
        _render_reason(ps or [], (k, l_), None),
        gr.update(),  # DO NOT update Radio from span clicks -> prevents second overwrite render
    )


# UI
with gr.Blocks(
    css=EXTRA_CSS, js=CUSTOM_JS, title="Semantic Mismatch — Full Pipeline"
) as demo:
    # top nav + title
    gr.Markdown("## SLeDoC")
    gr.HTML(nav_tag, visible=True)

    with gr.Tabs():
        with gr.Tab("Document Mismatch"):
            with gr.Row(elem_id="topline_row"):
                with gr.Column(scale=1):
                    doc1 = gr.File(
                        label="Document A (.docx / code / text)",
                        file_types=[
                            ".docx",
                            ".txt",
                            ".md",
                            ".py",
                            ".js",
                            ".ts",
                            ".java",
                            ".c",
                            ".cpp",
                            ".go",
                            ".rs",
                            ".rb",
                            ".php",
                            ".cs",
                            ".scala",
                            ".kt",
                            ".swift",
                        ],
                    )
                with gr.Column(scale=1):
                    doc2 = gr.File(
                        label="Document B (.docx / code / text)",
                        file_types=[
                            ".docx",
                            ".txt",
                            ".md",
                            ".py",
                            ".js",
                            ".ts",
                            ".java",
                            ".c",
                            ".cpp",
                            ".go",
                            ".rs",
                            ".rb",
                            ".php",
                            ".cs",
                            ".scala",
                            ".kt",
                            ".swift",
                        ],
                    )
                with gr.Column(scale=7):
                    with gr.Accordion("⚙️ Settings", open=False):
                        with gr.Row():
                            use_llm_12 = gr.Checkbox(
                                value=True, label="Use combined Extract+NLI (LLM)"
                            )
                            llm_model = gr.Dropdown(
                                choices=[
                                    "gpt-5",
                                    "claude-opus-4.6",
                                ],
                                value=DEFAULT_MODEL,
                                label="LLM model (for combined 1+2)",
                                allow_custom_value=True,
                            )
                            use_for_code = gr.Checkbox(
                                value=False,
                                label="Use for code (code-aware NLI prompt)",
                                info="Accepts code/text files and uses a code-specific NLI system prompt.",
                            )
                        with gr.Row():
                            nli_model = gr.Dropdown(
                                label="NLI model (when not using LLM 1+2)",
                                choices=MODELS_LIST,
                                value=MODELS_LIST[0] if MODELS_LIST else None,
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
                                0.5,
                                0.99,
                                value=0.90,
                                step=0.01,
                                label="Similarity threshold",
                            )
                        with gr.Row():
                            claim_prompt = gr.Textbox(
                                value=LLM_NLI_SYSTEM_PROMPT or DEFAULT_SYSTEM_PROMPT,
                                lines=8,
                                label="Claim extraction system prompt",
                            )
                        with gr.Row():
                            use_llm_contra = gr.Checkbox(
                                value=True,
                                label="Use LLM to extract contradicting terms",
                            )
                            contra_model = gr.Textbox(
                                value=DEFAULT_MODEL,
                                label="Model for term extraction",
                                scale=2,
                            )
                        with gr.Row():
                            dl_pairs = gr.File(
                                label="Download pairs.json", interactive=False
                            )
                        with gr.Row():
                            artifacts_json = gr.JSON(label="Artifacts", visible=False)
            with gr.Column(scale=1):
                run_btn = gr.Button("Run", variant="primary")

            # Legend row with Swap + labeled_spans download on the right
            with gr.Row(elem_id="legend_row"):
                gr.HTML(_legend_html(), elem_id="viewer_legend")
                with gr.Row(elem_id="legend_right"):
                    swap_btn = gr.Button(
                        "Swap", variant="secondary", elem_id="swap_button"
                    )
                    dl_labels_json = gr.DownloadButton(
                        label="Download spans", size="md", elem_id="dl_labels_btn"
                    )

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
                choices=["1"],
                value="1",
                label="Show Document B for paragraph…",
                interactive=False,
                visible=False,
            )

            # bridge for click events
            bridge_click = gr.Textbox(visible=False, elem_id="bridge_click")

            # hidden state
            pairs_state = gr.State([])
            align_path_state = gr.State("")
            pairs_path_state = gr.State("")

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
                llm_model_id,
                use_for_code_v,
            ):
                (align_path, pairs_path, preview, left_html, right, pairs) = (
                    _orchestrate(
                        doc1_f,
                        doc2_f,
                        bool(use_llm),
                        nli_model_id,
                        device_v,
                        int(bs),
                        int(win),
                        float(thr),
                        sys_prompt,
                        llm_model_id or DEFAULT_MODEL,
                        bool(use_for_code_v),
                    )
                )
                # Precompute contradiction terms once for all blocks so clicks are instant and stable
                try:
                    pairs = _precompute_contra_terms_for_all(
                        pairs,
                        bool(use_llm_contra),
                        (contra_model or DEFAULT_MODEL),
                    )
                except Exception:
                    # fail-safe: keep pairs as-is
                    pass

                # reasoning is empty until a specific span is clicked
                reason = _render_reason(pairs or [], (0, None), None)

                # Prepare Radio choices "1..N"
                choices = [str(i + 1) for i in range(len(pairs))]
                default = choices[0] if choices else None

                return (
                    left_html,
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
                        choices=choices,
                        value=default,
                        interactive=True,
                        visible=True,
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
                    llm_model,
                    use_for_code,
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

            # Swap handler: same as _run2 but with doc1/doc2 flipped
            def _swap_and_run(
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
                llm_model_id,
                use_for_code_v,
            ):
                # Simply call the orchestrator with swapped inputs
                return _run2(
                    doc2_f,  # <- swapped
                    doc1_f,  # <- swapped
                    use_llm,
                    nli_model_id,
                    device_v,
                    bs,
                    win,
                    thr,
                    sys_prompt,
                    use_llm_contra,
                    contra_model,
                    llm_model_id,
                    use_for_code_v,
                )

            swap_btn.click(
                _swap_and_run,
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
                    llm_model,
                    use_for_code,
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
                return gr.update(value=str(p), visible=True)

            def _build_labeled_spans_json(pairs):
                if not pairs:
                    return gr.update(visible=False)
                tmpdir = Path(tempfile.mkdtemp())
                outp = tmpdir / "labeled_spans.json"
                rows = []
                for k, b in enumerate(pairs or []):
                    out1 = b.get("output_1") or []
                    out2 = b.get("output_2") or []
                    idx1 = _index_claims(out1)
                    idx2 = _index_claims(out2)
                    parA = _text_left(b)
                    parB = _text_right(b)

                    # optional: help consumers find anchors easily
                    def _anchor_payload(r):
                        anc = r.get("anchor")
                        if isinstance(anc, int) and 0 <= anc < len(out1):
                            return anc, _get_claim_text(out1[anc])
                        return None, None

                    for r in b.get("nli_results") or []:
                        prem = str(r.get("premise_raw") or r.get("premise") or "")
                        hyp = str(r.get("hypothesis_raw") or r.get("hypothesis") or "")
                        lbl = str(r.get("label") or "").lower()
                        expl = str(
                            r.get("explanation")
                            or r.get("reason")
                            or r.get("reasoning")
                            or ""
                        )

                        prem_in_left = prem in idx1
                        hyp_in_right = hyp in idx2
                        prem_in_right = prem in idx2
                        hyp_in_left = hyp in idx1

                        li = None
                        rj = None
                        left_span = prem
                        right_span = hyp

                        # 1) Normal orientation (prem on A, hyp on B)
                        if prem_in_left or hyp_in_right:
                            li = idx1.get(prem) if prem_in_left else None
                            rj = idx2.get(hyp) if hyp_in_right else None
                            left_span, right_span = prem, hyp

                        # 2) True swap (only if BOTH sides actually match swapped)
                        elif prem_in_right and hyp_in_left:
                            li = idx1.get(hyp)
                            rj = idx2.get(prem)
                            left_span, right_span = hyp, prem

                        # 3) Unmatched → handle additions explicitly
                        else:
                            anc_idx = r.get("anchor")
                            anc_idx = (
                                anc_idx
                                if isinstance(anc_idx, int) and 0 <= anc_idx < len(out1)
                                else None
                            )
                            if lbl in ("addition", "neutral"):
                                # right-only addition
                                if hyp and hyp_in_right:
                                    li = anc_idx
                                    rj = idx2.get(hyp)
                                    left_span, right_span = "", hyp
                                # left-only addition
                                elif prem and prem_in_left:
                                    li = idx1.get(prem)
                                    rj = None
                                    left_span, right_span = prem, ""
                                else:
                                    li = anc_idx
                                    rj = None
                                    left_span, right_span = "", ""
                        anc_idx, anc_text = _anchor_payload(r)
                        rows.append(
                            {
                                "pair_index": k + 1,
                                "left_idx": li if li is not None else None,
                                "right_idx": rj if rj is not None else None,
                                "left_span": left_span,
                                "right_span": right_span,
                                "label": lbl,
                                "explanation": expl,
                                "anchor_idx": anc_idx,
                                "anchor_span": anc_text,
                                "paragraph_A": parA,
                                "paragraph_B": parB,
                            }
                        )
                outp.write_text(
                    json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                return str(outp)

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

            # Wire the download button to build JSON from pairs_state on click
            dl_labels_json.click(
                _build_labeled_spans_json, inputs=[pairs_state], outputs=dl_labels_json
            )

# Fast launch guard
if __name__ == "__main__":
    # queue to keep UI responsive during async + background work
    demo.queue().launch(show_error=True, share=True)
