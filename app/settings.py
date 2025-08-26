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


nav_tag = """
<div id="sidebar">
    <a href="/">Pipeline</a>
    <a href="/full_pipeline/">Full Pipeline</a>
    <a href="/pipeline-llm/">Pipeline-LLM</a>
    <a href="/pipeline-llm-new/">Pipeline-LLM-NEW</a>
    <a href="/nli/">NLI Viewer</a>
    <a href="/convert/">Convert CSV</a>
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

# скрипт курсора + показывает скор уверенности
CUSTOM_JS = """
() => {
  const confBox = () => document.getElementById('conf_box');

  const hi = (id, col) => {
    const e = document.getElementById(id);
    if (!e) return;
    if (e.classList.contains('selected')) {
      // don't override selected color on hover
      return;
    }
    if (!('_bg' in e.dataset)) e.dataset._bg = e.style.backgroundColor || '';
    e.style.backgroundColor = col || e.style.backgroundColor;
    e.style.outline = '2px solid #000';
  };

  const bye = (id) => {
    const e = document.getElementById(id);
    if (!e) return;
    if (e.classList.contains('selected')) {
      // keep selected color on mouseout
      return;
    }
    const bg = ('_bg' in e.dataset) ? e.dataset._bg : '';
    e.style.backgroundColor = bg || '';
    e.style.outline = '';
  };

  const clearSelection = () => {
    document.querySelectorAll('span.hl.selected, span.hl.dimmed')
      .forEach(el => { el.classList.remove('selected','dimmed'); });
    document.querySelectorAll('span.hl').forEach(el => {
      // restore any styles
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
}
"""
