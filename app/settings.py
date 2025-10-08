SIDEBAR_CSS = """
/* Sidebar placed on the left bottom */
#sidebar{
    position:fixed;             /* stay in place when scrolling */
    left:0;                     /* stick to left edge */
    bottom:0;                   /* stick to bottom edge */
    width:140px;                /* fixed width of a sidebar */

    /* look & feel */
    background:#202124;         /* dark gray background */
    color:#fff;                 /* white text */
    padding:12px 8px;           /* inner padding */
    box-sizing:border-box;      /* include padding in width */

    display:flex;               /* flex container */
    flex-direction:column;      /* stack items vertically */
    gap:8px;                    /* space between items */
}

/* buttons inside the bar */
#sidebar a{
    display:block;              /* make links block-level */
    padding:8px 4px;            /* inner padding */
    border-radius:4px;          /* rounded corners */
    color:#fff;                 /* white text */
    text-decoration:none;       /* no underline */
    text-align:center;          /* center text */
    background:#3d4043;         /* slightly lighter bg */
    font-weight:600;            /* semi-bold text */
    font-size:14px;             /* slightly larger text */
}
#sidebar a:hover{
    background:#5f6368;         /* background of a button when hover */
}

/* keep main app shifted right so it doesn’t sit under the bar */
body {
  margin-left:140px !important; /* move main content to the reight to not cover with sidebar */
}
"""


nav_tag = """
<div id="sidebar">
    <a href="/pipeline-llm-new/">Pipeline-LLM-NEW</a>
</div>
"""


# Base visual language used across the app (cards, badges, highlights)
BASE_CSS = """
/* Cards for paragraphs */
/* Styles for paragraph cards: border, padding, rounded corners, margin, white background, subtle shadow */
.para-box{
  border:1px solid #adb5bd;
  padding:12px;
  border-radius:12px;
  margin:12px 0;
  background:#fff;
  box-shadow:0 1px 3px rgba(0,0,0,.05);
}

/* Paragraph header: small font, gray color, bottom margin */
.para-head{
  font-size:12px;                        /* smaller font size */
  color:#667085;                         /* gray color */
  margin-bottom:6px;                     /* space below header */
}

/* Claim spans */
/* Highlighted claim spans: relative positioning, small horizontal padding, rounded corners, pointer cursor */
.hl{
  position:relative;
  padding:0 3px;
  border-radius:5px;
  cursor:pointer;
}
/* Dashed outline on hover for claim spans */
.hl:hover{
  outline:1px dashed #888;
}


/* NLI palette (soft) */
/* Background colors for NLI labels: entailment (green), neutral (blue), contradiction (red) */
.hl.entailment { background: rgba(34,197,94,.18); }
.hl.neutral { background: rgba(59,130,246,.18); }
.hl.addition { background: rgba(59,130,246,.18); }
.hl.contradiction { background: rgba(244,63,94,.18); }
/* When an addition is shown with delta tokens, we softly wash it green (entailment feel) */
.hl.as-entailment { background: rgba(34,197,94,.18) !important; }


/* Explicit contradiction terms highlight */
/* Highlight for contradiction terms: yellow background, small padding, rounded corners */
.contra-term{
 background:#fff59a;
  padding:0 2px;
  border-radius:4px;
}

/* Selection and dimming */
/* Selected claim span: solid outline, inner shadow */
.hl.selected{
 outline:2px solid #111;
  box-shadow:0 0 0 3px rgba(0,0,0,.06) inset;
}
/* Dimmed claim span: reduced saturation and brightness */
.hl.dimmed{
  filter:saturate(.3) brightness(.95);
}
/* Stronger, visible dimming in the left pane */
#left_pane .hl.dimmed{
  opacity:.35;
  filter:grayscale(.25) saturate(.2) brightness(.85);
  transition:opacity .12s ease, filter .12s ease;
}
/* Right-pane dimming (light, but visible). Keep anchor/mate bright. */
#right_pane .hl.dimmed{
  opacity:.5;
  filter: grayscale(.1) saturate(.4) brightness(.9);
  transition: opacity .12s ease, filter .12s ease;
}
/* Force-anchor highlight (color set via --anchor-color; brackets handled in EXTRA_CSS) */
.anchor-hl{
  background:transparent !important;
  outline:2px solid var(--anchor-color, #16a34a) !important;
}
.anchor-inline{ padding:0 2px; border-radius:4px; }

/* Simple badge */
/* Badge styles: inline-block, small padding, fully rounded, small font */
.badge{
  display:inline-block;
  padding:2px 6px;
  border-radius:9999px;
  font-size:11px;
}
/* Danger badge: light red background, dark red text */
.badge-danger{
  background:#fee2e2;
  color:#b91c1c;
}
/* Info badge: light blue background, dark blue text */
.badge-info{
  background:#dbeafe;
  color:#1d4ed8;
}

/* Hide Gradio’s default block padding around HTML blocks for tighter stacking */
/* Remove default Gradio padding for HTML blocks in left and right panes */
#left_pane .gr-html, #right_pane .gr-html{
  padding:0 !important;
}

/* Reasoning title */
/* Reasoning block title: no top margin, bottom margin, bold font */
#reason_box h3 {
  margin: 0 0 8px 0;
  font-weight: 700;
}
"""


# Viewer-level constants (colors, reasons, severity)
HOVER_PALETTE = {
    "contradiction": "#ffd6c2",  # soft red-ish
    "neutral": "rgba(59,130,246,.28)",  # blue (legacy neutral)
    "addition": "rgba(59,130,246,.28)",  # blue (kept separate for clarity)
    "entailment": "#d6ffd6",  # soft green
}

NLI_SEVERITY = {"contradiction": 3, "addition": 2, "neutral": 2, "entailment": 1}

NLI_REASON_BY_LABEL = {
    "equivalent": "спаны идентичны",
    "entailment": "спаны идентичны",
    "contradiction": "противоречие между утверждениями",
    "addition": "дополнение / новая информация",
    "neutral": "дополнение / новая информация",
}

# Viewer CSS that used to live inline in full_pipeline_new.py
VIEWER_CSS = """
/* dual-pane viewer layout */
.left-pane  { flex: 2 1 0; min-width: 420px; }
.right-pane { flex: 1 1 0; position: static; max-height: 80vh; overflow:auto; }
#viewer_row { align-items: stretch; }
#left_pane, #right_pane { display: block; }

/* paragraph card: compact, borderless, lightly indented with spacing */
.para-box{
  border: 0;
  padding: 4px 0 10px 8px;
  margin: 12px 0;
  background: transparent;
  box-shadow: none;
}
.para-head { display:none; }
.para-inner { line-height: 1.45; }

/* claim spans */
.hl{ position:relative; padding:0 3px; border-radius:5px; cursor:pointer; }
.hl:hover { outline:1px dashed #888; }

/* NLI colors — keep them faint */
.hl.entailment     { background: rgba(34,197,94,.18); }
.hl.neutral        { background: rgba(59,130,246,.18); }
.hl.addition       { background: rgba(59,130,246,.18); } /* blue */
.hl.contradiction  { background: rgba(244,63,94,.18); }
/* When an addition is shown with delta tokens, we softly wash it green (entailment feel) */
.hl.as-entailment { background: rgba(34,197,94,.18) !important; }

/* contradiction term highlight */
.contra-term{ background: #fff59a; padding:0 2px; border-radius:3px; }

/* selected state */
.hl.selected { outline:2px solid #000 }

/* mute tooltip artifacts — but keep ::after available for anchors */
.hl:not(.anchor-hl)::after { display:none !important; }

/* colored, bracketed anchors on demand (color via --anchor-color set by JS) */
.hl.anchor-hl{
  background:transparent !important;
  outline:2px solid var(--anchor-color, #16a34a) !important;
}
.hl.anchor-hl::before { content:"["; color:var(--anchor-color, #16a34a); font-weight:700; }
.hl.anchor-hl::after  { content:"]"; color:var(--anchor-color, #16a34a); font-weight:700; display:inline; }

.mirror-box{
  border:1px solid #adb5bd;
  padding:12px;
  border-radius:12px;
  background:#fafafa;
  min-height:140px;
  margin:12px 0;
}
.left-pane  .para-box:first-child,
.right-pane .mirror-box:first-child { margin-top: 0; }
.viewer-wrap { display:flex; gap:16px; align-items:stretch; }
.anch{ font-size:11px; opacity:.8; margin-left:4px; text-decoration:none; }

/* legend + confidence UI */
.toolbar { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin:8px 0; }
.legend { display:flex; gap:12px; align-items:center; font-size:12px; color:#475569; }
.legend .key { display:inline-flex; align-items:center; gap:6px; }
.legend .dot { width:10px; height:10px; border-radius:2px; display:inline-block; }
.legend .dot.ent { background:#22c55e; }
.legend .dot.con { background:#f43f5e; }
.legend .dot.neu { background:#3b82f6; }

.para-box{ min-height: unset; }
.mirror-box{ min-height: unset; }

#right_pane { position: static; max-height: 80vh; overflow-y: auto; }

/* reasoning panel */
.reason-wrap { margin-top: 4px; display: flex; flex-direction: column; gap: 8px; }
.reason-title { font-weight: 800; margin: 3px 0 3px; font-size: 16px; }
.reason-card { border: 2px solid #334155; background: #ffffff; padding: 10px 12px; border-radius: 12px; font-size: 14px; font-weight: 500; box-shadow: 0 2px 6px rgba(0,0,0,.06); }

/* contradiction focus box (kept for future use) */
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
    max-height: 80vh;
    overflow-y: auto;
}
.left-pane .para-box { margin: 8px 0; }
.left-title{ font-weight:700; font-size:14px; color:#334155; margin:4px 4px 10px 4px; opacity:.9; }
.right-title{ font-weight:700; font-size:14px; color:#334155; margin:4px 4px 10px 4px; opacity:.9; }
.left-pane .para-box.para-focus { outline: 2px solid #334155; }
.left-pane .para-box.para-dim   { opacity: .55; filter: saturate(.6); }
#topline_row { align-items: flex-end; gap:12px; }
#topline_row .gr-accordion { margin: 0; }
"""

# All the custom JS for interactivity and alignment
CUSTOM_JS = """
() => {
  /* ===== Shadow DOM helpers (Gradio) ===== */
  const appEl  = () => document.querySelector("gradio-app");
  const root   = () => (appEl() && appEl().shadowRoot) ? appEl().shadowRoot : document;
  const q      = (sel) => root().querySelector(sel);
  const qa     = (sel) => root().querySelectorAll(sel);

  /* Which left paragraph (pair) is focused + which left spans must stay bright */
  const current = {
    idx: null,
    keepIds: [],          // LEFT keep-bright span IDs
    dimLeftAll: false,    // remember “dim all left spans” across repaints
    anchorIds: [],        // LEFT anchors to re-bracket after repaint
    keepRightIds: [],     // RIGHT keep-bright span IDs
    anchorRightIds: [],   // RIGHT anchors to re-bracket after repaint
    selectedLeftId: null, // persist selection across repaint
    selectedRightId: null
  };

  /* ===== Visual helpers (hover + selection) ===== */
  const confBox = () => q('#conf_box');

  const hi = (id, col) => {
    const e = q('#' + CSS.escape(id));
    if (!e) return;
    if (e.classList.contains('selected')) return; // keep selection strong
    if (!('_bg' in e.dataset)) e.dataset._bg = e.style.backgroundColor || '';
    // Only apply color if provided; passing null keeps current background
    if (col != null) e.style.backgroundColor = col || e.style.backgroundColor;
    e.style.outline = '2px solid #000';
  };

  const bye = (id) => {
    const e = q('#' + CSS.escape(id));
    if (!e) return;
    if (e.classList.contains('selected')) return;
    const bg = ('_bg' in e.dataset) ? e.dataset._bg : '';
    e.style.backgroundColor = bg || '';
    e.style.outline = '';
  };

  const clearSelection = () => {
    qa('span.hl.selected, span.hl.dimmed, span.hl.anchor-hl').forEach(el => {
      el.classList.remove('selected','dimmed','anchor-hl');
      el.style.removeProperty('--anchor-color');
    });
    current.selectedLeftId = null;
    current.selectedRightId = null;
    qa('span.hl').forEach(el => {
      const bg = ('_bg' in el.dataset) ? el.dataset._bg : '';
      el.style.backgroundColor = bg || '';
      el.style.outline = '';
    });
    if (confBox()) confBox().textContent = 'Confidence: -';
  };

  /* Color + bracket an anchor with its own label color (or mate color) */
  function forceAnchor(el){
    if (!el) return;
    const col = el.dataset.selfcolor || el.dataset.hcolor || '#16a34a';
    el.style.setProperty('--anchor-color', col);
    el.classList.add('anchor-hl');
  }

  /* span dimming in LEFT pane */
  function dimLeftSpansExcept(keepIds = []) {
    const keep = new Set(keepIds);
    qa('#left_pane .hl').forEach(el => {
      if (keep.has(el.id)) {
        el.classList.remove('dimmed');
      } else {
        el.classList.add('dimmed');
      }
    });
  }
  function clearLeftSpanDimming(){
    qa('#left_pane .hl.dimmed').forEach(el => el.classList.remove('dimmed'));
  }

  /* span dimming in RIGHT pane */
  function dimRightSpansExcept(keepIds = []) {
    const keep = new Set(keepIds);
    qa('#right_pane .hl').forEach(el => {
      if (keep.has(el.id)) {
        el.classList.remove('dimmed');
      } else {
        el.classList.add('dimmed');
      }
    });
  }
  function clearRightSpanDimming(){
    qa('#right_pane .hl.dimmed').forEach(el => el.classList.remove('dimmed'));
  }

  /* ===== Paragraph dimming (left pane) ===== */
  function dimParagraphs(idx){
    if (idx == null) return;
    qa('#left_pane .para-box').forEach(pb => {
      const p = pb.getAttribute('data-idx');
      if (p === String(idx)) {
        pb.classList.add('para-focus');
        pb.classList.remove('para-dim');
      } else {
        pb.classList.remove('para-focus');
        pb.classList.add('para-dim');
      }
    });
  }
  function clearParagraphDimming(){
    qa('#left_pane .para-box').forEach(pb => pb.classList.remove('para-dim','para-focus'));
  }

  /* Reapply paragraph + span dimming after Gradio re-renders the left HTML */
  (function observeLeftRepaints(){
    const L = q('#left_pane');
    if (!L || !('MutationObserver' in window)) return;
    const obs = new MutationObserver(() => {
      // DOM replaced → reapply dimming for the current idx (if any)
      if (current.idx != null) dimParagraphs(current.idx);
      // Reapply span dimming (clicked set) after repaint
      if (current.keepIds && current.keepIds.length){
        setTimeout(() => {
          dimLeftSpansExcept(current.keepIds);
          // re-apply “dim all left” even if keepIds is empty (persisted flag)
        }, 0);
      } else if (current.dimLeftAll) {
        setTimeout(() => {
          qa('#left_pane .hl').forEach(el => {
            el.classList.add('dimmed');
          });
          // also re-apply forced anchor brackets on the LEFT (lost on re-render)
          (current.anchorIds || []).forEach(id => {
            const el = q('#' + CSS.escape(id));
            if (el) forceAnchor(el);
          });
          // re-select the previously selected LEFT span if any
          if (current.selectedLeftId) {
            const el = q('#' + CSS.escape(current.selectedLeftId));
            if (el) {
              el.classList.add('selected');
              el.classList.remove('dimmed');    // ensure it’s bright after repaint
              el.style.outline = '2px solid #000';
            }
          }
        }, 0);
      }
    });
    obs.observe(L, { childList: true, subtree: true, characterData: true });
  })();

  /* Reapply RIGHT dimming/anchors after right HTML repaints */
  (function observeRightRepaints(){
    const R = q('#right_pane');
    if (!R || !('MutationObserver' in window)) return;
    const obs = new MutationObserver(() => {
      if (current.keepRightIds && current.keepRightIds.length){
        setTimeout(() => {
          dimRightSpansExcept(current.keepRightIds);
          (current.anchorRightIds || []).forEach(id => {
            const el = q('#' + CSS.escape(id));
            if (el) forceAnchor(el);
          });
          // re-select the previously selected RIGHT span if any
          if (current.selectedRightId) {
            const el = q('#' + CSS.escape(current.selectedRightId));
            if (el) {
              el.classList.add('selected');
              el.classList.remove('dimmed');   // mirror left-side fix
              el.style.outline = '2px solid #000';
            }
          }
        }, 0);
      }
    });
    obs.observe(R, { childList: true, subtree: true, characterData: true });
  })();

  /* ===== Bridge to Python (hidden textbox) ===== */
  function findBridgeBox(){
    return q('#bridge_click textarea, #bridge_click input');
  }
  function sendBridge(val){
    const box = findBridgeBox();
    if (!box) return false;
    box.value = val;
    box.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true }));
    return true;
  }

  /* ===== Hover feedback (cross-highlight left/right) ===== */
  root().addEventListener('mouseover', ev => {
    const t = (ev.composedPath && ev.composedPath()[0]) || ev.target;
    const s = t && t.closest ? t.closest('span.hl') : null;
    if (s) {
      const tgt = s.dataset.target || '';
      // For ADDITION: keep the hovered span blue; color only its mate/anchor.
      if (s.dataset.kind === 'addition') {
        hi(s.id, null); // don't repaint self bg
        if (tgt) hi(tgt, s.dataset.hcolor || '');
      } else {
        hi(s.id, s.dataset.hcolor || '');
        if (tgt) hi(tgt, s.dataset.hcolor || '');
      }
      const c = parseFloat(s.dataset.conf || '');
      if (confBox()) confBox().textContent = 'Confidence: ' + (isNaN(c) ? '-' : c.toFixed(3));
    }
  }, {capture:true});

  root().addEventListener('mouseout', ev => {
    const t = (ev.composedPath && ev.composedPath()[0]) || ev.target;
    const s = t && t.closest ? t.closest('span.hl') : null;
    if (s) {
      const tgt = s.dataset.target || '';
      bye(s.id);
      if (tgt) bye(tgt);
    }
  }, {capture:true});

  /* ===== Click handling (no scrolling, no floating) ===== */
  root().addEventListener('click', function (e) {
    const path = e.composedPath ? e.composedPath() : [e.target];
    let target = null;
    for (const n of path) {
      if (n instanceof Element && n.matches && (n.matches('.hl') || n.matches('.para-box'))) {
        target = n; break;
      }
    }

    // A) Click on a highlighted LEFT span
    const span = target && target.matches('.hl') ? target : null;
    if (span && span.hasAttribute('data-pair') && span.hasAttribute('data-left')) {
      e.preventDefault();
      e.stopPropagation();

      clearSelection(); // only clear span selection; dimming handled below
      span.classList.add('selected');

      const mateId = span.dataset.target;
      // no fill on select — keep only the box
      span.style.outline = '2px solid #000';
      current.selectedLeftId = span.id;
      current.selectedRightId = mateId || null;
      if (mateId) {
        const mate = q('#' + CSS.escape(mateId));
        if (mate) {
          mate.classList.add('selected');
          mate.style.outline = '2px solid #000';
          mate.classList.remove('dimmed'); // ensure it is not dimmed on first paint
          // If LEFT click was on an "addition" span, force its mate (anchor) to green
          if (span.dataset.kind === 'addition') forceAnchor(mate);
        }
      }
      // RIGHT dimming: keep mate + right in-pane anchor if any
      const keepRight = [];
      if (mateId) keepRight.push(mateId);
      if (span.dataset.kind === 'addition' && span.dataset.ranchor) keepRight.push(span.dataset.ranchor);
      dimRightSpansExcept(keepRight);
      current.keepRightIds = keepRight.slice();
      current.anchorRightIds = [];
      if (span.dataset.kind === 'addition') {
        if (span.dataset.ranchor) current.anchorRightIds.push(span.dataset.ranchor);
      }
      // build "keep bright" set for left spans (clicked + its left-anchor if addition)
      const keep = [span.id];
      if (span.dataset.kind === 'addition' && span.dataset.lanchor) {
        keep.push(span.dataset.lanchor);
        // also green the left in-pane anchor itself
        const lEl = q('#' + CSS.escape(span.dataset.lanchor));
        if (lEl) lEl.classList.add('anchor-hl');
      }
      // Dim all other LEFT spans + remember this set for re-renders
      dimLeftSpansExcept(keep);
      current.keepIds = keep.slice();
      current.anchorIds = [];
      if (span.dataset.kind === 'addition') {
        if (span.dataset.lanchor) current.anchorIds.push(span.dataset.lanchor);
        if (span.dataset.selfanchor === '1') current.anchorIds.push(span.id);
      }

      // force-highlight the LEFT in-pane anchor when present
      if (span.dataset.kind === 'addition') {
        const la = span.dataset.lanchor;
        if (la) forceAnchor(q('#' + CSS.escape(la)));
        // And the RIGHT in-pane anchor when present (if we clicked a left span and it embeds right anchors too)
        const ra = span.dataset.ranchor;
        if (ra) forceAnchor(q('#' + CSS.escape(ra)));
        // Self-anchored: also bracket the clicked span itself to “green with brackets”
        if (span.dataset.selfanchor === '1') {
          forceAnchor(span);
        }
      }

      const pidx = parseInt(span.getAttribute('data-pair') || '0', 10);
      const lidx = span.getAttribute('data-left');
      // apply paragraph dimming immediately for snappy feel
      current.idx = pidx;
      dimParagraphs(current.idx);

      if (sendBridge(`S:${pidx}:${lidx}`)) {
        // no-op; already dimmed above
      }
      e.stopImmediatePropagation();
      return;
    }

    // C) Click on a highlighted RIGHT span
    if (span && span.hasAttribute('data-pair') && span.hasAttribute('data-right')) {
      e.preventDefault();
      e.stopPropagation();

      clearSelection();
      span.classList.add('selected');
      span.style.outline = '2px solid #000';
      current.selectedRightId = span.id;

      const mateId = span.dataset.target; // points to L-k-li
      // Fallback: for additions without data-target, try left anchor
      const laFallback = span.dataset.lanchor || '';
      current.selectedLeftId = mateId || null;
      if (mateId) {
        const mate = q('#' + CSS.escape(mateId));
        if (mate) {
          mate.classList.add('selected');
          mate.style.outline = '2px solid #000';
          mate.classList.remove('dimmed'); // guarantee not dimmed on first click
          // If RIGHT click was on an "addition" span, force its mate (anchor) to green
          if (span.dataset.kind === 'addition') forceAnchor(mate);
        }
      }

      // RIGHT dimming: keep selected right span + its right in-pane anchor (if any)
      const keepR = [span.id];
      if (span.dataset.kind === 'addition' && span.dataset.ranchor) keepR.push(span.dataset.ranchor);
      dimRightSpansExcept(keepR);
      current.keepRightIds = keepR.slice();
      // default: we are NOT in “dim all left” mode unless proven otherwise below
      current.dimLeftAll = false;
      current.anchorRightIds = [];
      if (span.dataset.kind === 'addition') {
        if (span.dataset.ranchor) current.anchorRightIds.push(span.dataset.ranchor);
        // Self-anchored: bracket the clicked span itself too
        if (span.dataset.selfanchor === '1') {
          forceAnchor(span);
          current.anchorRightIds.push(span.id);
        }
      }
      // dim all other LEFT spans, keep only the left anchor (and/or left mate) bright
      const keep = [];
      if (mateId) keep.push(mateId);
      // try anchor fallback for additions
      if (!mateId && laFallback) {
        keep.push(laFallback);
        current.selectedLeftId = laFallback;
      }
      if (span.dataset.kind === 'addition' && span.dataset.lanchor) {
        keep.push(span.dataset.lanchor);
      }
      if (keep.length) {
        dimLeftSpansExcept(keep);
        current.dimLeftAll = false;
      } else {
        // No known left mate yet → DIM ALL left spans until Python resolves a mate.
        qa('#left_pane .hl').forEach(el => el.classList.add('dimmed'));
        current.dimLeftAll = true;
      }
      current.keepIds = keep.slice();     // always refresh keepIds
      // persist left anchor so we can re-apply brackets after re-render
      current.anchorIds = [];
      if (span.dataset.kind === 'addition') {
        const la = span.dataset.lanchor || mateId;
        if (la) {
          current.anchorIds = [la];
          const lEl = q('#' + CSS.escape(la));
          if (lEl) forceAnchor(lEl);
        }
      }

      // force-highlight the RIGHT in-pane anchor (anchor claim on the same B paragraph)
      if (span.dataset.kind === 'addition') {
        const ra = span.dataset.ranchor;
        if (ra) forceAnchor(q('#' + CSS.escape(ra)));
        // And the LEFT in-pane anchor (when addition is on the right)
        const la = span.dataset.lanchor;
        if (la) forceAnchor(q('#' + CSS.escape(la)));
      }

      const pidx = parseInt(span.getAttribute('data-pair') || '0', 10);
      const ridx = span.getAttribute('data-right');
      // apply paragraph dimming immediately; prevents “first click looks dimmed”
      current.idx = pidx;
      dimParagraphs(current.idx);

      if (sendBridge(`R:${pidx}:${ridx}`)) {
        // already set above
      }
      e.stopImmediatePropagation();
      return;
    }

    // B) Click on a LEFT paragraph card (anywhere on the card)
    const para = target && target.matches('.para-box') ? target : null;
    if (para && para.hasAttribute('data-idx')) {
      const idx = parseInt(para.getAttribute('data-idx') || '0', 10);
      if (sendBridge(`P:${idx}`)) {
        current.idx = idx;
        dimParagraphs(current.idx);   // only dim, no scroll, no float
        // Clear span dimming if user clicks the card background
        clearLeftSpanDimming();
        clearRightSpanDimming();
        current.keepIds = [];
        current.keepRightIds = [];
        current.dimLeftAll = false;   // reset
        current.anchorIds = [];
        current.anchorRightIds = [];
        current.selectedLeftId = null;
        current.selectedRightId = null;
      }
    e.stopImmediatePropagation();
    return;
    }
  }, {capture:true});

  /* Clear dimming only when clicking outside BOTH panes (and not on a claim) */
  root().addEventListener('click', function (e) {
    const left  = q('#left_pane');
    const right = q('#right_pane');
    if (!left) return;

    const t = (e.composedPath && e.composedPath()[0]) || e.target;
    // If the click is inside either pane or on a claim span, don't clear.
    if ((left.contains(t) || (right && right.contains(t))) ||
        (t.closest && t.closest('span.hl'))) {
      return;
    }

    // Clicked outside the viewer → clear everything
    current.idx = null;
    clearParagraphDimming();
    clearLeftSpanDimming();
    clearRightSpanDimming();
    current.keepIds = [];
    current.keepRightIds = [];
    current.dimLeftAll = false;   // reset on outside click
    current.anchorIds = [];
    current.anchorRightIds = [];
  }, {capture:true});
}
"""
