from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

# All the custom JS for interactivity and alignment with anchors
CUSTOM_JS_PATH = ROOT_DIR / "app" / "web" / "custom.js"
CUSTOM_JS = CUSTOM_JS_PATH.read_text(encoding="utf-8")

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
