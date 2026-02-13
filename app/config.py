import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env once, centrally
load_dotenv()


def _env_str(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if (v is not None and v != "") else default


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    try:
        return int(v) if v is not None else default
    except ValueError:
        return default


def load_prompt(env_key: str, file_env_key: str, default_text: str) -> str:
    """
    Priority:
      1) <file_env_key> points to a file -> read it
      2) <env_key> contains the prompt inline
      3) default_text (code fallback)
    """
    path = _env_str(file_env_key, None)
    if path:
        p = Path(path).expanduser()
        try:
            return p.read_text(encoding="utf-8").strip()
        except Exception:
            pass  # fall through
    val = _env_str(env_key, None)
    if val:
        return val
    return default_text


def first_existing_path(*candidates: str) -> str | None:
    from pathlib import Path

    for c in candidates:
        if not c:
            continue
        p = Path(c).expanduser()
        if p.exists() and p.is_file():
            return str(p)
    return None


LLM_LANG = os.getenv("LLM_LANG", "ru").lower()  # "ru" or "en"


def resolve_default_prompt_path(prefix: str) -> str | None:
    """
    Try common filenames inside ./prompts.
    Handles your current naming, including the 'defaut' typo.
    """
    base = Path("prompts")
    candidates = [
        base / f"{prefix}.{LLM_LANG}.md",
        base / f"{prefix}.ru.md",
        base / f"{prefix}.en.md",
        # handle 'default' vs 'defaut'
        base / f"{prefix.replace('default', 'defaut')}.{LLM_LANG}.md",
        base / f"{prefix.replace('default', 'defaut')}.ru.md",
        base / f"{prefix.replace('default', 'defaut')}.en.md",
    ]
    return first_existing_path(*map(str, candidates))


# Prompt resolution with file → env → default fallback
_p_llm = resolve_default_prompt_path("llm_nli_system")
_p_llm_code = resolve_default_prompt_path("llm_nli_system_code")
_p_align = resolve_default_prompt_path("llm_align_default")

LLM_NLI_SYSTEM_PROMPT: str = load_prompt(
    "LLM_NLI_SYSTEM_PROMPT",
    "LLM_NLI_SYSTEM_PROMPT_FILE",
    default_text=(Path(_p_llm).read_text(encoding="utf-8").strip() if _p_llm else ""),
)
LLM_NLI_SYSTEM_PROMPT_CODE: str = load_prompt(
    "LLM_NLI_SYSTEM_PROMPT_CODE",
    "LLM_NLI_SYSTEM_PROMPT_CODE_FILE",
    default_text=(
        Path(_p_llm_code).read_text(encoding="utf-8").strip() if _p_llm_code else ""
    ),
)
CLAIM_EXTRACTOR_SYSTEM_PROMPT: str = load_prompt(
    "CLAIM_EXTRACTOR_SYSTEM_PROMPT",
    "CLAIM_EXTRACTOR_SYSTEM_PROMPT_FILE",
    default_text=(
        Path(_p_align).read_text(encoding="utf-8").strip() if _p_align else ""
    ),
)

# Public config
LLM_MAX_PARALLEL: int = _env_int("LLM_MAX_PARALLEL", 8)
DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
