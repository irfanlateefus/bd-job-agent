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


# --- US location filtering (filters.us_only) --------------------------------
US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}
_US_RE = re.compile(r"\b(u\.?s\.?a?|united states)\b", re.IGNORECASE)
_STATE_RE = re.compile(r"\b[A-Z]{2}\b")  # uppercase 2-letter tokens (e.g. "NY")
_NON_US = [
    # countries / regions
    "united kingdom", "england", "scotland", "ireland", "france", "germany", "spain",
    "italy", "netherlands", "portugal", "poland", "sweden", "norway", "denmark",
    "finland", "switzerland", "austria", "belgium", "czech", "romania", "greece",
    "canada", "mexico", "brazil", "argentina", "chile", "colombia", "india",
    "singapore", "japan", "china", "hong kong", "taiwan", "korea", "australia",
    "new zealand", "israel", "united arab emirates", "saudi", "egypt", "south africa",
    "nigeria", "emea", "apac", "latam", "anz",
    # hub cities
    "london", "paris", "dublin", "berlin", "munich", "frankfurt", "amsterdam", "madrid",
    "barcelona", "lisbon", "milan", "rome", "zurich", "geneva", "stockholm", "copenhagen",
    "oslo", "helsinki", "warsaw", "prague", "vienna", "brussels", "toronto", "montreal",
    "vancouver", "ottawa", "bengaluru", "bangalore", "hyderabad", "mumbai", "delhi",
    "gurgaon", "pune", "chennai", "noida", "tokyo", "osaka", "seoul", "beijing",
    "shanghai", "shenzhen", "sydney", "melbourne", "auckland", "tel aviv", "dubai",
    "abu dhabi", "sao paulo", "são paulo", "mexico city", "bogota", "santiago",
]


def is_us_location(loc: str) -> bool:
    """Best-effort US check. True for US or unknown; False only when clearly
    non-US. Conservative: explicit US markers win (so multi-region roles that
    include the US are kept), and bare 'Remote' / unknown locations are kept."""
    if not loc:
        return True
    if _US_RE.search(loc) or any(t in US_STATES for t in _STATE_RE.findall(loc)):
        return True
    low = loc.lower()
    if any(m in low for m in _NON_US):
        return False
    return True
