"""
Shared config loader + fast, rule-based pre-filter.

is_relevant() runs BEFORE any LLM call so we never pay to score obviously
irrelevant listings. All keywords come from config.yaml — nothing is hardcoded.
"""
import re
from functools import lru_cache
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def load_config() -> dict:
    """Load and cache config.yaml from the project root."""
    path = PROJECT_ROOT / "config.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _compile(keywords: list[str]) -> list[re.Pattern]:
    # Word-boundary match so short tokens like "BD" / "GTM" don't match inside
    # unrelated words, while multi-word phrases ("business development") still work.
    return [re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE) for k in keywords if k]


def load_personas() -> list[dict]:
    """Return [{name, keywords, context}] with each persona's context file loaded."""
    out = []
    for p in load_config().get("personas", []) or []:
        cf = PROJECT_ROOT / (p.get("context_file") or "")
        out.append({
            "name": p.get("name", "?"),
            "keywords": p.get("keywords", []) or [],
            "context": cf.read_text() if cf.exists() else "",
        })
    return out


def _required_keywords() -> list[str]:
    """Union of every persona's keywords — the pre-filter passes any of them."""
    kws: list[str] = []
    for p in load_config().get("personas", []) or []:
        kws.extend(p.get("keywords", []) or [])
    return kws


def is_relevant(text: str) -> bool:
    """
    True when `text` matches at least one persona keyword (union across all
    personas) and no blocked keyword. Used on titles (and HN comment bodies).
    """
    if not text:
        return False
    blocked = _compile(load_config().get("filters", {}).get("blocked_keywords", []) or [])
    required = _compile(_required_keywords())

    if blocked and any(p.search(text) for p in blocked):
        return False
    if not required:
        return True
    return any(p.search(text) for p in required)
