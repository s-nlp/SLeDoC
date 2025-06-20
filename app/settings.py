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
    <a href="/mismatch/">Mismatch</a>
    <a href="/nli/">NLI</a>
    <a href="/nli-predict/">NLI Predict</a>
</div>
"""