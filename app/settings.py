side_bar_left_top = """
/* ── left nav bar ────────────────────────────────────────────────────── */
#sidebar{
    position:fixed; left:0; top:0; bottom:0; width:140px;
    background:#202124; color:#fff; padding:12px 8px; box-sizing:border-box;
    display:flex; flex-direction:column; gap:8px;
}
#sidebar a{
    display:block; padding:8px 4px; border-radius:4px;
    color:#fff; text-decoration:none; text-align:center;
    background:#3d4043; font-weight:600; font-size:14px;
}
#sidebar a:hover{ background:#5f6368; }
body{ margin-left:140px !important; }   /* push the app aside */
"""


side_bar = """
/* ── left-bottom nav bar ─────────────────────────────────────────────── */
#sidebar{
    position:fixed;
    left:0;                       /* stick to left edge */
    bottom:0;                     /* stick to bottom edge */
    width:140px;

    /* look & feel */
    background:#202124;
    color:#fff;
    padding:12px 8px;
    box-sizing:border-box;

    display:flex;
    flex-direction:column;
    gap:8px;
}

/* buttons inside the bar */
#sidebar a{
    display:block;
    padding:8px 4px;
    border-radius:4px;
    color:#fff;
    text-decoration:none;
    text-align:center;
    background:#3d4043;
    font-weight:600;
    font-size:14px;
}
#sidebar a:hover{
    background:#5f6368;
}

/* keep main app shifted right so it doesn’t sit under the bar */
body{ margin-left:140px !important; }
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


# NLI VIEWER
# поведение курсора и подсветки в NLI Viewer
EXTRA_CSS = """
.para-box{
    border:1px solid #000; padding:8px; min-height:320px; min-width:320px;
}
/* вид курсора - pointer*/
.hl{position:relative; cursor:pointer;}
/* какой цвет будет у выделенного span при нажатии */
.hl.selected     { outline:2px solid #000; }
/* какой цвет будет у других span при нажатии на выделенный */
.hl.dimmed       { opacity:.35; }
/* что будет показываться при нажатии курсором */
.hl:hover::after,.hl:focus::after{ content:none; display:none; }
"""

# скрипт курсора + показывает скор уверенности + правое окно
CUSTOM_JS = """
() => {
  const confBox = () => document.getElementById('conf_box');

  const hi = (id, col) => {
    const e = document.getElementById(id);
    if (!e) return;
    if (e.classList.contains('selected')) return; // keep selected color
    if (!('_bg' in e.dataset)) e.dataset._bg = e.style.backgroundColor || '';
    e.style.backgroundColor = col || e.style.backgroundColor;
    e.style.outline = '2px solid #000';
  };

  const bye = (id) => {
    const e = document.getElementById(id);
    if (!e) return;
    if (e.classList.contains('selected')) return; // keep selected color
    const bg = ('_bg' in e.dataset) ? e.dataset._bg : '';
    e.style.backgroundColor = bg || '';
    e.style.outline = '';
  };

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

  document.addEventListener('mouseout', ev => {
    const s = ev.target.closest('span.hl');
    if (s) {
      const tgt = s.dataset.target || '';
      bye(s.id);
      if (tgt) bye(tgt);
    }
  });

  // click = lock selection with the same (green/red/blue) color
  document.addEventListener('click', ev => {
    const span = ev.target.closest('span.hl');
    if (!span) {
      // clicked outside any span ⇒ clear selection
      clearSelection();
      return;
    }

    // clicked on a span ⇒ reset previous, then select this pair
    clearSelection();

    const targetId = span.dataset.target;
    const col = span.dataset.hcolor || '';

    // select clicked
    span.classList.add('selected');
    span.style.backgroundColor = col;
    span.style.outline = '2px solid #000';

    // select counterpart if exists
    if (targetId) {
      const mate = document.getElementById(targetId);
      if (mate) {
        mate.classList.add('selected');
        const mcol = mate.dataset.hcolor || col;
        mate.style.backgroundColor = mcol;
        mate.style.outline = '2px solid #000';
      }
    }

    // dim others
    document.querySelectorAll('span.hl:not(.selected)')
      .forEach(el => el.classList.add('dimmed'));
  });

  // ---- Bridge clicks from left viewer to hidden Gradio Textbox (#bridge_click) ----
  const findBridgeBox = () =>
    document.querySelector('#bridge_click textarea') ||
    document.querySelector('#bridge_click input');

  document.addEventListener('click', function (e) {
    // Click on a highlighted span with mapping metadata
    const span = e.target.closest('.hl');
    if (span && span.hasAttribute('data-pair') && span.hasAttribute('data-left')) {
      e.stopPropagation();
      // local selection highlight
      document.querySelectorAll('.hl.selected').forEach(el => el.classList.remove('selected'));
      span.classList.add('selected');

      const pidx = span.getAttribute('data-pair');
      const lidx = span.getAttribute('data-left');
      const box = findBridgeBox();
      if (box) {
        box.value = "S:" + pidx + ":" + lidx;
        box.dispatchEvent(new Event('input',  { bubbles: true }));
        box.dispatchEvent(new Event('change', { bubbles: true }));
      }
      return;
    }

    // Click on a paragraph box (card)
    const para = e.target.closest('.para-box');
    if (para && para.hasAttribute('data-idx')) {
      const idx = para.getAttribute('data-idx');
      const box = findBridgeBox();
      if (box) {
        box.value = "P:" + idx;
        box.dispatchEvent(new Event('input',  { bubbles: true }));
        box.dispatchEvent(new Event('change', { bubbles: true }));
      }
      // Schedule alignment to the same row after Gradio re-renders
      setTimeout(function(){ scheduleAlign(idx); }, 60);
    }
  }, true);

  // ===================== ROW ALIGNMENT (merged safely) ======================
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

  // =================== STRICT 1↔1 ROW ALIGNMENT BY data-idx ===================
  function alignRightToLeftByIdx() {
    const left = Array.from(document.querySelectorAll('#left_pane .para-box[data-idx]'));
    const right = Array.from(document.querySelectorAll('#right_pane .mirror-box[data-idx]'));
    if (!left.length || !right.length) return;

    // reset previous adjustments
    right.forEach(rb => { rb.style.marginTop = ''; });

    // map left boxes by data-idx
    const leftByIdx = {};
    left.forEach(lb => { leftByIdx[lb.getAttribute('data-idx')] = lb; });

    // baseline tops (so we work in the same relative coordinate space)
    const left0 = left[0].getBoundingClientRect().top;
    const right0 = right[0].getBoundingClientRect().top;

    // for each right box, align to the left with the same data-idx
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

  // simple throttle to avoid doing too much work during resize/renders
  let _alignTimer = null;
  function scheduleAlignByIdx(delay=80) {
    if (_alignTimer) clearTimeout(_alignTimer);
    _alignTimer = setTimeout(() => {
      _alignTimer = null;
      alignRightToLeftByIdx();
      scheduleEqualize(60);
    }, delay);
  }

  // run on load, resize, and after your bridge-driven updates
  window.addEventListener('load', () => scheduleAlignByIdx(250));
  window.addEventListener('resize', () => scheduleAlignByIdx(50));

  // hook into your existing click logic: after "P:<idx>" bridge update, align
  document.addEventListener('click', function(e){
    const para = e.target && e.target.closest ? e.target.closest('.para-box[data-idx]') : null;
    if (para) {
      // give Gradio a moment to re-render right column, then align
      scheduleAlignByIdx(120);
    }
  }, true);

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

  // small scheduler so we run after the DOM has settled
  function scheduleEqualize(delay = 80) {
    setTimeout(equalizePaneHeights, delay);
  }

  // Observe DOM changes inside the panes and re-equalize
  (function observePanes(){
    const L = document.getElementById('left_pane');
    const R = document.getElementById('right_pane');
    if (!L || !R || !('MutationObserver' in window)) return;

    const obs = new MutationObserver(() => scheduleEqualize(40));
    const opts = { childList: true, subtree: true, characterData: true };
    obs.observe(L, opts);
    obs.observe(R, opts);
  })();


  function scheduleAlign(idx){
    // Try a few times to wait for Gradio DOM updates
    var attempts = 0;
    function tick(){
      attempts++;
      var ok = (idx != null) ? alignPair(idx) : (alignAll(), true);
      if (attempts < 8 && !ok){
        setTimeout(tick, 80);
      } else if (attempts < 8) {
        // one more pass after content settles
        setTimeout(function(){ (idx != null) ? alignPair(idx) : alignAll(); }, 120);
      }
    }
    setTimeout(tick, 80);
  }

  window.addEventListener('load', function(){
    setTimeout(function(){ scheduleAlign(null); }, 250);
  });
  window.addEventListener('resize', function(){
    scheduleAlign(null);
  });
}
"""
