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
  /* =========================
     Helpers for Shadow DOM
     ========================= */
  const appEl  = () => document.querySelector("gradio-app");
  const root   = () => (appEl() && appEl().shadowRoot) ? appEl().shadowRoot : document;
  const q      = (sel) => root().querySelector(sel);
  const qa     = (sel) => root().querySelectorAll(sel);

  /* Track the currently focused left paragraph index */
  const current = { idx: null };

  /* Option: keep selected paragraph centered inside the LEFT pane scroller */
  const CENTER_ON_MOVE = true;
  function centerViewportOnLeft(idx){
    try{
      const L  = q('#left_pane');
      const lb = q(`#left_pane .para-box[data-idx="${idx}"]`);
      if (!L || !lb) return;

      // compute 'y' = offsetTop of lb relative to #left_pane
      let y = 0, node = lb;
      while (node && node !== L) {
        y += node.offsetTop || 0;
        node = node.offsetParent;
      }
      const target = Math.max(0, Math.round(y - (L.clientHeight/2 - lb.offsetHeight/2)));
      L.scrollTo({ top: target, behavior: 'smooth' });
    }catch(_){}
  }

  /* ============ Visual helpers ============ */
  const confBox = () => q('#conf_box');

  const hi = (id, col) => {
    const e = q('#' + CSS.escape(id));
    if (!e) return;
    if (e.classList.contains('selected')) return;
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
    qa('span.hl.selected, span.hl.dimmed').forEach(el => el.classList.remove('selected','dimmed'));
    qa('span.hl').forEach(el => {
      const bg = ('_bg' in el.dataset) ? el.dataset._bg : '';
      el.style.backgroundColor = bg || '';
      el.style.outline = '';
    });
    if (confBox()) confBox().textContent = 'Confidence: -';
  };

  /* ============ Bridge to Python ============ */
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

  /* ============ Floating right panel alignment ============ */
  function leftPane()  { return q('#left_pane'); }
  function rightPane() { return q('#right_pane'); }

  function moveFloatToIdx(idx){
    const lb    = q(`#left_pane .para-box[data-idx="${idx}"]`);
    const float = q('#float_box');
    const track = q('#right_track');
    const L     = leftPane();
    if (!lb || !float || !track || !L) return false;

    // offset of lb relative to #left_pane
    let y = 0, node = lb;
    while (node && node !== L) {
      y += node.offsetTop || 0;
      node = node.offsetParent;
    }
    y = Math.max(0, Math.round(y));
    float.style.transform = `translateY(${y}px)`;
    return true;
  }

  function syncRightTrackHeight(){
    const L = leftPane();
    const track = q('#right_track');
    if (L && track) track.style.height = L.scrollHeight + 'px';
  }

  function scheduleAlign(idx){
    let tries = 0;
    const tick = () => {
      tries++;
      syncRightTrackHeight();
      const hasFloat = !!q('#float_box');
      const ok = hasFloat ? (idx != null ? moveFloatToIdx(idx) : true) : false;
      if (tries < 10 && !ok) setTimeout(tick, 90);
    };
    requestAnimationFrame(() => setTimeout(tick, 60));
  }

  /* Keep track height in sync as DOM changes */
  (function observePanes(){
    const L = leftPane();
    const R = rightPane();
    if (!L || !R || !('MutationObserver' in window)) return;
    const obs = new MutationObserver(() => setTimeout(syncRightTrackHeight, 50));
    obs.observe(L, { childList: true, subtree: true, characterData: true });
    obs.observe(R, { childList: true, subtree: true, characterData: true });

    // ✅ While user scrolls the LEFT pane, keep the float glued to the selected paragraph
    L.addEventListener('scroll', () => {
      if (current.idx != null) moveFloatToIdx(current.idx);
    }, { passive: true });
  })();

  /* ============ Hover feedback ============ */
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

  /* ============ Click handling (UNIVERSAL BRIDGE) ============ */
  root().addEventListener('click', function (e) {
    const path = e.composedPath ? e.composedPath() : [e.target];
    let target = null;
    for (const n of path) {
      if (n instanceof Element && n.matches && (n.matches('.hl') || n.matches('.para-box'))) {
        target = n; break;
      }
    }

    // A) Click on a highlighted span
    const span = target && target.matches('.hl') ? target : null;
    if (span && span.hasAttribute('data-pair') && span.hasAttribute('data-left')) {
      e.preventDefault();
      e.stopPropagation();

      clearSelection();
      span.classList.add('selected');
      const targetId = span.dataset.target;
      const col = span.dataset.hcolor || '';
      span.style.backgroundColor = col;
      span.style.outline = '2px solid #000';
      if (targetId) {
        const mate = q('#' + CSS.escape(targetId));
        if (mate) {
          mate.classList.add('selected');
          mate.style.backgroundColor = mate.dataset.hcolor || col;
          mate.style.outline = '2px solid #000';
        }
      }
      const pidx = parseInt(span.getAttribute('data-pair') || '0', 10);
      const lidx = span.getAttribute('data-left');

      if (sendBridge(`S:${pidx}:${lidx}`)) {
        current.idx = pidx;
        scheduleAlign(current.idx);
        if (CENTER_ON_MOVE) centerViewportOnLeft(current.idx);
      }
      return;
    }

    // B) Click on a left paragraph card
    const para = target && target.matches('.para-box') ? target : null;
    if (para && para.hasAttribute('data-idx')) {
      const idx = parseInt(para.getAttribute('data-idx') || '0', 10);
      if (sendBridge(`P:${idx}`)) {
        current.idx = idx;
        scheduleAlign(current.idx);
        if (CENTER_ON_MOVE) centerViewportOnLeft(current.idx);
      }
    }
  }, {capture:true});

  /* Initial alignment + window resize */
  window.addEventListener('load',  () => setTimeout(() => scheduleAlign(current.idx), 250));
  window.addEventListener('resize', () => scheduleAlign(current.idx));
}
"""
