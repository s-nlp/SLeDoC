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


# nav_tag = """
# <div id="sidebar">
#     <a href="/">Pipeline</a>
#     <a href="/full_pipeline/">Full Pipeline</a>
#     <a href="/pipeline-llm/">Pipeline-LLM</a>
#     <a href="/pipeline-llm-new/">Pipeline-LLM-NEW</a>
#     <a href="/nli/">NLI Viewer</a>
#     <a href="/convert/">Convert CSV</a>
# </div>
# """
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
  // Small helper to find optional confidence UI label
  const confBox = () => document.getElementById('conf_box');

  // Temporarily highlight an element by ID (used for hover-in)
  // Stores the original background color in data._bg on first hover so we can restore it later.
  const hi = (id, col) => {
    const e = document.getElementById(id);
    if (!e) return;
    if (e.classList.contains('selected')) return; // don't override a locked selection
    if (!('_bg' in e.dataset)) e.dataset._bg = e.style.backgroundColor || '';
    e.style.backgroundColor = col || e.style.backgroundColor;
    e.style.outline = '2px solid #000';
  };

  // Revert highlight on an element by ID (used for hover-out)
  // Restores original background color and outline from the cached value.
  const bye = (id) => {
    const e = document.getElementById(id);
    if (!e) return;
    if (e.classList.contains('selected')) return; // keep locked selection intact
    const bg = ('_bg' in e.dataset) ? e.dataset._bg : '';
    e.style.backgroundColor = bg || '';
    e.style.outline = '';
  };

  // Clear all visual selections/dimming + optional confidence readout
  const clearSelection = () => {
    document.querySelectorAll('span.hl.selected, span.hl.dimmed')
      .forEach(el => { el.classList.remove('selected','dimmed'); });
    document.querySelectorAll('span.hl').forEach(el => {
      const bg = ('_bg' in el.dataset) ? el.dataset._bg : '';
      el.style.backgroundColor = bg || '';
      el.style.outline = '';
    });
    if (confBox()) confBox().textContent = 'Confidence: -';
  };

  // Hover-in: highlight current span and its counterpart; update confidence label if present
  document.addEventListener('mouseover', ev => {
    const s = ev.target.closest('span.hl');
    if (s) {
      const tgt = s.dataset.target || '';
      hi(s.id, s.dataset.hcolor || '');
      if (tgt) hi(tgt, s.dataset.hcolor || '');
      const c = parseFloat(s.dataset.conf || '');
      if (confBox()) confBox().textContent = 'Confidence: ' + (isNaN(c) ? '-' : c.toFixed(3));
    }
  });

  // Hover-out: remove temporary highlight on current span and its counterpart
  document.addEventListener('mouseout', ev => {
    const s = ev.target.closest('span.hl');
    if (s) {
      const tgt = s.dataset.target || '';
      bye(s.id);
      if (tgt) bye(tgt);
    }
  });

  // Click on any .hl span()
  // 1) Clear previous selection
  // 2) Lock selection on the clicked span (+ counterpart if exists)
  // 3) Dim other spans in the same pair (for visual focus)
  document.addEventListener('click', ev => {
    const span = ev.target.closest('span.hl');
    if (!span) {
      // Clicked outside spans: clear selection
      clearSelection();
      return;
    }

    // Reset old selection, then apply a new one
    clearSelection();

    const targetId = span.dataset.target;
    const col = span.dataset.hcolor || '';

    // Mark clicked span as selected
    span.classList.add('selected');
    span.style.backgroundColor = col;
    span.style.outline = '2px solid #000';

    // Select counterpart if exists
    if (targetId) {
      const mate = document.getElementById(targetId);
      if (mate) {
        mate.classList.add('selected');
        const mcol = mate.dataset.hcolor || col;
        mate.style.backgroundColor = mcol;
        mate.style.outline = '2px solid #000';
      }
    }

    // Dim all non-selected spans from the same pair index
    const pair = span.getAttribute('data-pair');
    document.querySelectorAll('.hl.dimmed').forEach(el => el.classList.remove('dimmed'));
    document.querySelectorAll(`.hl[data-pair="${pair}"]:not(.selected)`).forEach(el => el.classList.add('dimmed'));
  });

  // Bridge clicks from the viewer to hidden Gradio Textbox (#bridge_click)
  const findBridgeBox = () =>
    document.querySelector('#bridge_click textarea') ||
    document.querySelector('#bridge_click input');

  // Pending index for alignment. When a click triggers a backend update that will
  // re-render the right pane, we record the pair index here. Once the DOM
  // mutation observer fires (indicating new content has been inserted), the
  // observer will call scheduleAlign on this index to re-sync the floating
  // panel with the corresponding paragraph. After aligning the value is reset.
  window._pendingAlignIdx = null;

  /*
    Universal click bridge:

    - When a user clicks on any highlighted span (.hl), we extract the associated pair
      and left-index and send a signal to the Gradio backend via the hidden Textbox.
      This works for both left spans (which carry data-left) and right spans (which
      have a data-target attribute pointing back to a left span ID like "L-0-2").
      We no longer stop propagation here so that the general click handler (defined
      earlier) can handle visual highlighting and dimming.  After dispatching the
      backend update we schedule an alignment of the floating right panel so it
      tracks the corresponding paragraph height.

    - When a paragraph card (.para-box) is clicked, we send a "P:<idx>" signal to
      select that entire pair (focus on paragraph) and schedule the right panel to
      align with that paragraph.
  */
  document.addEventListener('click', function (e) {
    const span = e.target.closest('.hl');
    if (span && span.hasAttribute('data-pair')) {
      // Determine pair index from the span's dataset
      let pidx = span.getAttribute('data-pair');
      let lidx = span.getAttribute('data-left');

      // For right-side spans we don't have data-left, but we do have a data-target
      // attribute of the form "L-<pair>-<left>". Parse it to get the pair and left indexes.
      if (!lidx && span.dataset.target) {
        const m = span.dataset.target.match(/L-(\d+)-(\d+)/);
        if (m) {
          pidx = m[1];
          lidx = m[2];
        }
      }

      // If we have both pair and left index, send an "S:<pair>:<left>" update
      if (pidx != null && lidx != null) {
        const box = findBridgeBox();
        if (box) {
          // Write into the bridge textbox and dispatch only an 'input' event.  The
          // additional 'change' event previously dispatched caused Gradio to
          // interpret the value twice, which resulted in duplicate backend calls
          // and a second re-render that cleared the right pane.  Emitting
          // solely the 'input' event avoids this duplicate update.
          box.value = "S:" + pidx + ":" + lidx;
          box.dispatchEvent(new Event('input', { bubbles: true }));
        }
        // Record the pending index so observer can align after DOM updates
        window._pendingAlignIdx = parseInt(pidx);
        // Do not stop propagation; let the general click handler update visuals
        return;
      }
    }

    // Paragraph click (left side)
    const para = e.target.closest('.para-box');
    if (para && para.hasAttribute('data-idx')) {
      const idx = para.getAttribute('data-idx');
      const box = findBridgeBox();
      if (box) {
        // signal: focus = (pair, None). Only dispatch the 'input' event to
        // trigger the backend update once.  Sending a 'change' event here
        // previously caused the right pane to be redrawn a second time and
        // effectively removed the selection.  See notes above.
        box.value = "P:" + idx;
        box.dispatchEvent(new Event('input', { bubbles: true }));
      }
      // Record the pending index so observer can align after DOM updates
      window._pendingAlignIdx = parseInt(idx);
    }
  }, true);

  // (LEGACY) ROW ALIGNMENT HELPERS
  // alignPair / alignAll / alignRightToLeftByIdx are kept for backward compatibility
  // when you render one right card per left paragraph (non-floating mode).
  function alignPair(idx){
    var L = document.querySelector('#left_pane .para-box[data-idx="' + idx + '"]');
    var R = document.querySelector('#right_pane .mirror-box[data-idx="' + idx + '"]');
    if (!L || !R) return false;
    var h = Math.ceil(L.getBoundingClientRect().height);
    if (h > 0) R.style.minHeight = h + 'px';
    try { L.scrollIntoView({block:'start', behavior:'smooth'}); } catch(_) {}
    try { R.scrollIntoView({block:'start', behavior:'smooth'}); } catch(_) {}
    return true;
  }

  function alignAll(){
    var left = document.querySelectorAll('#left_pane .para-box[data-idx]');
    if (!left.length) return;
    for (var i=0; i<left.length; i++){
      var lb = left[i];
      var idx = lb.getAttribute('data-idx');
      var rb = document.querySelector('#right_pane .mirror-box[data-idx="' + idx + '"]');
      if (!rb) continue;
      var h = Math.ceil(lb.getBoundingClientRect().height);
      rb.style.minHeight = h > 0 ? (h + 'px') : '';
    }
  }

  // Strict by-index alignment (legacy) — matches right cards to left cards 1:1
  function alignRightToLeftByIdx() {
    const left = Array.from(document.querySelectorAll('#left_pane .para-box[data-idx]'));
    const right = Array.from(document.querySelectorAll('#right_pane .mirror-box[data-idx]'));
    if (!left.length || !right.length) return;

    // reset previous adjustments
    right.forEach(rb => { rb.style.marginTop = ''; });

    // map left boxes by data-idx
    const leftByIdx = {};
    left.forEach(lb => { leftByIdx[lb.getAttribute('data-idx')] = lb; });

    // compute relative offset baselines within both columns
    const left0 = left[0].getBoundingClientRect().top;
    const right0 = right[0].getBoundingClientRect().top;

    // shift each right box so its top equals the corresponding left box top
    right.forEach(rb => {
      const idx = rb.getAttribute('data-idx');
      const lb  = leftByIdx[idx];
      if (!lb) return;  // skip if that idx doesn't exist on the left

      const desired = Math.round(lb.getBoundingClientRect().top - left0);
      const current = Math.round(rb.getBoundingClientRect().top - right0);
      const delta = desired - current;

      // push this right box down/up so its top equals the left's top
      rb.style.marginTop = delta + 'px';
    });
  }

  // Throttled legacy aligner (used only if floating panel isn't present)
  let _alignTimer = null;
  function scheduleAlignByIdx(delay=80) {
    if (_alignTimer) clearTimeout(_alignTimer);
    _alignTimer = setTimeout(() => {
      _alignTimer = null;
      alignRightToLeftByIdx();
      scheduleEqualize(60);
    }, delay);
  }

  // Equalize total heights of left/right panes (cosmetic)
  function equalizePaneHeights() {
    const L = document.getElementById('left_pane');
    const R = document.getElementById('right_pane');
    if (!L || !R) return;

    // clear previous min-heights so we measure natural sizes
    L.style.minHeight = '';
    R.style.minHeight = '';

    // Use offsetHeight (layouted height); scrollHeight also works if content overflows
    const h = Math.max(L.offsetHeight, R.offsetHeight);
    // apply the same min-height to both
    L.style.minHeight = h + 'px';
    R.style.minHeight = h + 'px';
  }

  // Floating Right Panel helpers
  function leftPane()  { return document.getElementById('left_pane'); }
  function rightPane() { return document.getElementById('right_pane'); }

  // Main align orchestrator:
  // If floating box exists → slide it to the clicked paragraph.
  // Else → fall back to legacy row alignment.
  function scheduleAlign(idx){
    var attempts = 0;
    function tick(){
      attempts++;
      syncRightTrackHeight();

      var ok = false;
      // If we have a floating box, move it. Else, fall back to old per-row alignment.
      if (document.getElementById('float_box')) {
        ok = (idx != null) ? moveFloatToIdx(idx) : true;
      } else {
        ok = (idx != null) ? alignPair(idx) : (alignAll(), true);  // your legacy functions
      }

      // Try a few times to wait out DOM re-renders
      if (attempts < 8 && !ok) {
        setTimeout(tick, 80);
      } else if (attempts < 8) {
        setTimeout(function(){
          syncRightTrackHeight();
          if (document.getElementById('float_box') && idx != null) moveFloatToIdx(idx);
        }, 120);
      }
    }
    setTimeout(tick, 80);
  }

  // Keep the invisible right track as tall as the left column
  function syncRightTrackHeight(){
    const L = leftPane();
    const track = document.getElementById('right_track');
    if (L && track) track.style.height = L.scrollHeight + 'px';
  }

  // Slide the floating right box to the vertical position of the target left paragraph
  function moveFloatToIdx(idx){
    const lb    = document.querySelector('#left_pane .para-box[data-idx="' + idx + '"]');
    const float = document.getElementById('float_box');
    const track = document.getElementById('right_track');
    const L     = document.getElementById('left_pane');
    if (!lb || !float || !track || !L) return false;

    // Use offsetTop relative to the left pane to be immune to viewport scroll / reflow jitter
    let y = 0, node = lb;
    while (node && node !== L) {
      y += node.offsetTop || 0;
      node = node.offsetParent;
    }
    y = Math.max(0, Math.round(y));

    float.style.transform = 'translateY(' + y + 'px)';
    return true;
  }

  // small scheduler so we run after the DOM has settled
  function scheduleEqualize(delay = 80) {
    setTimeout(equalizePaneHeights, delay);
  }

  // Observe dynamic DOM changes inside panes and keep heights in sync
  (function observePanes(){
    const L = document.getElementById('left_pane');
    const R = document.getElementById('right_pane');
    if (!L || !R || !('MutationObserver' in window)) return;

    const obs = new MutationObserver(() => {
      // Equalize pane heights (cosmetic)
      scheduleEqualize(40);
      // If a click previously recorded a pending pair index, align the floating
      // panel after new DOM has been inserted. Then clear the flag.
      if (window._pendingAlignIdx !== null && window._pendingAlignIdx !== undefined) {
        try {
          scheduleAlign(window._pendingAlignIdx);
        } catch (e) {}
        window._pendingAlignIdx = null;
      }
    });
    const opts = { childList: true, subtree: true, characterData: true };
    obs.observe(L, opts);
    obs.observe(R, opts);
  })();

  // Kick off initial alignment and keep it responsive
  window.addEventListener('load', function(){ setTimeout(function(){ scheduleAlign(null); }, 250); });
  window.addEventListener('resize', function(){ scheduleAlign(null); });
}
"""
