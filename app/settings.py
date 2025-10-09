from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / "web"  # app/web


def _read(name: str) -> str:
    return (ASSETS_DIR / name).read_text(encoding="utf-8")


# Base visual language used across the app (cards, badges, highlights)
BASE_CSS = _read("base.css")

# Sidebar CSS that used to live inline in full_pipeline_new.py
SIDEBAR_CSS = _read("sidebar.css")

# Viewer CSS that used to live inline in full_pipeline_new.py
VIEWER_CSS = _read("viewer.css")

# All the custom JS for interactivity and alignment with anchors
CUSTOM_JS = _read("custom.js")

# Viewer-level constants (colors, reasons, severity)
HOVER_PALETTE = {
    "contradiction": "#ffd6c2",  # soft red-ish
    "neutral": "rgba(59,130,246,.28)",  # blue (legacy neutral)
    "addition": "rgba(59,130,246,.28)",  # blue (kept separate for clarity)
    "entailment": "#d6ffd6",  # soft green
}

# Severity (1-3) for each NLI label; used to pick the “most severe” match when multiple
NLI_SEVERITY = {"contradiction": 3, "addition": 2, "neutral": 2, "entailment": 1}

# reason descriptions by label
NLI_REASON_BY_LABEL = {
    "equivalent": "спаны идентичны",
    "entailment": "спаны идентичны",
    "contradiction": "противоречие между утверждениями",
    "addition": "дополнение / новая информация",
    "neutral": "дополнение / новая информация",
}

# Navigation HTML snippet for sidebar used in full_pipeline_new.py
nav_tag = """
<div id="sidebar">
    <a href="/pipeline-llm-new/">Pipeline-LLM-NEW</a>
</div>
"""
