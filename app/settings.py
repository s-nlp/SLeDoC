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
    <a href="/mismatch/">Mismatch Viewer</a>
    <a href="/nli/">NLI Viewer</a>
    <a href="/convert/">Convert CSV</a>
    <a href="/full_pipeline/">Full Pipeline</a>
    <a href="/pipeline-llm/">Pipeline-LLM</a>
</div>
"""


# NLI VIEWER
# поведение курсора и подсветки в NLI Viewer
EXTRA_CSS = """
.para-box{
    border:1px solid #000; padding:8px; min-height:320px; min-width:320px;
}
.hl{position:relative; cursor:help;}
/* какой цвет будет у span при нажатии */
.hl.selected     { outline:2px solid #000; }
.hl.dimmed       { opacity:.35; }
.hl:hover::after,.hl:focus::after{
    content:attr(data-claim);
    position:absolute; left:0; top:100%;
    max-width:1000px; min-width:240px; white-space:pre-wrap;
    z-index:10; background:#333; color:#fff; padding:6px 8px; border-radius:4px;
    font-size:13px; line-height:1.3; box-shadow:0 2px 6px rgba(0,0,0,.25);
}
"""

# скрипт курсора + показывает скор уверенности
CUSTOM_JS = """
() => {
  const confBox = () => document.getElementById('conf_box');
  const hi   = (id,col) => { const e=document.getElementById(id);
    if(!e)return; e.dataset._bg=e.style.backgroundColor;
    e.style.backgroundColor=col; e.style.outline='2px solid #000'; };
  const bye  = id => { const e=document.getElementById(id);
    if(!e||!e.dataset._bg)return;
    e.style.backgroundColor=e.dataset._bg; e.style.outline=''; };

  document.addEventListener('mouseover', ev=>{
      const s=ev.target.closest('span.hl');
      if(s){
        const tgt=s.dataset.target || '';
        hi(s.id, s.dataset.hcolor || '');
        if(tgt) hi(tgt, s.dataset.hcolor || '');
        const c=parseFloat(s.dataset.conf||'');
        if(confBox()) confBox().textContent = 'Confidence: ' + (isNaN(c)?'-':c.toFixed(3));
      }
  });
  document.addEventListener('mouseout', ev=>{
      const s=ev.target.closest('span.hl');
      if(s){
        const tgt=s.dataset.target || '';
        bye(s.id);
        if(tgt) bye(tgt);
      }
  });
    /* click = lock / unlock */
    document.addEventListener('click', ev=>{
    const span = ev.target.closest('span.hl');
    if(!span) return;

    /* Clear previous selection */
    document.querySelectorAll('span.hl.selected, span.hl.dimmed')
            .forEach(el => { el.classList.remove('selected','dimmed'); });

    /* Select the clicked span and its counterpart (if any) */
    const targetId = span.dataset.target;
    span.classList.add('selected');
    if(targetId){
        const mate = document.getElementById(targetId);
        if(mate) mate.classList.add('selected');
    }

    /* Dim every other span to emphasise the pair */
    document.querySelectorAll('span.hl:not(.selected)')
            .forEach(el => el.classList.add('dimmed'));
    });
}
"""
