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
/* Stronger, visible dimming only in the left pane */
#left_pane .hl.dimmed{
  opacity:.35;
  filter:grayscale(.25) saturate(.2) brightness(.85);
  transition:opacity .12s ease, filter .12s ease;
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

# All the custom JS for interactivity and alignment
CUSTOM_JS = """
() => {
  /* ===== Shadow DOM helpers (Gradio) ===== */
  const appEl  = () => document.querySelector("gradio-app");
  const root   = () => (appEl() && appEl().shadowRoot) ? appEl().shadowRoot : document;
  const q      = (sel) => root().querySelector(sel);
  const qa     = (sel) => root().querySelectorAll(sel);

  /* Which left paragraph (pair) is focused + which left spans must stay bright */
  const current = { idx: null, keepIds: [] };

  /* ===== Visual helpers (hover + selection) ===== */
  const confBox = () => q('#conf_box');

  const hi = (id, col) => {
    const e = q('#' + CSS.escape(id));
    if (!e) return;
    if (e.classList.contains('selected')) return; // keep selection strong
    if (!('_bg' in e.dataset)) e.dataset._bg = e.style.backgroundColor || '';
    e.style.backgroundColor = col || e.style.backgroundColor;
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
        // ensure content is present before applying
        setTimeout(() => dimLeftSpansExcept(current.keepIds), 0);
      }
    });
    obs.observe(L, { childList: true, subtree: true, characterData: true });
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
      hi(s.id, s.dataset.hcolor || '');
      if (tgt) hi(tgt, s.dataset.hcolor || '');
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
      if (mateId) {
        const mate = q('#' + CSS.escape(mateId));
        if (mate) {
          mate.classList.add('selected');
          mate.style.outline = '2px solid #000';
          // If LEFT click was on an "addition" span, force its mate (anchor) to green
          if (span.dataset.kind === 'addition') forceAnchor(mate);
        }
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

      // force-highlight the LEFT in-pane anchor when present
      if (span.dataset.kind === 'addition') {
        const la = span.dataset.lanchor;
        if (la) forceAnchor(q('#' + CSS.escape(la)));
        // And the RIGHT in-pane anchor when present (if we clicked a left span and it embeds right anchors too)
        const ra = span.dataset.ranchor;
        if (ra) forceAnchor(q('#' + CSS.escape(ra)));
      }

      const pidx = parseInt(span.getAttribute('data-pair') || '0', 10);
      const lidx = span.getAttribute('data-left');

      if (sendBridge(`S:${pidx}:${lidx}`)) {
        current.idx = pidx;
        dimParagraphs(current.idx);   // ← NEW: only dim, no scroll, no float
      }
      return;
    }

    // C) Click on a highlighted RIGHT span
    if (span && span.hasAttribute('data-pair') && span.hasAttribute('data-right')) {
      e.preventDefault();
      e.stopPropagation();

      clearSelection();
      span.classList.add('selected');
      span.style.outline = '2px solid #000';

      const mateId = span.dataset.target; // points to L-k-li
      if (mateId) {
        const mate = q('#' + CSS.escape(mateId));
        if (mate) {
          mate.classList.add('selected');
          mate.style.outline = '2px solid #000';
          // If RIGHT click was on an "addition" span, force its mate (anchor) to green
          if (span.dataset.kind === 'addition') forceAnchor(mate);
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
      if (sendBridge(`R:${pidx}:${ridx}`)) {
        current.idx = pidx;
        dimParagraphs(current.idx);
      }
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
        current.keepIds = [];
      }
    }
  }, {capture:true});

  /* Optional: clear dimming if user clicks empty space in left pane */
  root().addEventListener('click', function (e) {
    const left = q('#left_pane');
    if (!left) return;
    if (left.contains(e.target)) {
      // clicks already handled above
    } else {
      current.idx = null;
      clearParagraphDimming();
      clearLeftSpanDimming();
      current.keepIds = [];
    }
  }, {capture:true});
}
"""
