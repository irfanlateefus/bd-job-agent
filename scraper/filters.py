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


def is_relevant(text: str) -> bool:
    """
    True when `text` contains at least one required keyword and no blocked
    keyword. Used on titles (and on HN comment bodies).
    """
    if not text:
        return False
    filters = load_config().get("filters", {}) or {}
    required = _compile(filters.get("required_keywords", []) or [])
    blocked = _compile(filters.get("blocked_keywords", []) or [])

    if blocked and any(p.search(text) for p in blocked):
        return False
    if not required:
        return True
    return any(p.search(text) for p in required)
