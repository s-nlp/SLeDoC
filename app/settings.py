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
/* Force-anchor highlight used on addition click */
.anchor-hl{ background: rgba(34,197,94,.35) !important; }  /* strong green on demand */
/* Optional: make bracketed anchors a bit tighter */
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

  /* Which left paragraph (pair) is focused */
  const current = { idx: null };

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
    qa('span.hl.selected, span.hl.dimmed, span.hl.anchor-hl').forEach(el => el.classList.remove('selected','dimmed','anchor-hl'));
    qa('span.hl').forEach(el => {
      const bg = ('_bg' in el.dataset) ? el.dataset._bg : '';
      el.style.backgroundColor = bg || '';
      el.style.outline = '';
    });
    if (confBox()) confBox().textContent = 'Confidence: -';
  };

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

  /* Reapply dimming after Gradio re-renders the left HTML */
  (function observeLeftRepaints(){
    const L = q('#left_pane');
    if (!L || !('MutationObserver' in window)) return;
    const obs = new MutationObserver(() => {
      // DOM replaced → reapply dimming for the current idx (if any)
      if (current.idx != null) dimParagraphs(current.idx);
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
          if (span.dataset.kind === 'addition') {
            mate.classList.add('anchor-hl');
          }
        }
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
          if (span.dataset.kind === 'addition') {
            mate.classList.add('anchor-hl');
          }
        }
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
        dimParagraphs(current.idx);   // ← NEW: only dim, no scroll, no float
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
    }
  }, {capture:true});
}
"""
