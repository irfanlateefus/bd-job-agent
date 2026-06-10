"""
Orchestrator: COLLECT -> ENRICH -> STORE.

  1. Fetch from every source (each isolated; a failure logs and continues).
  2. Deduplicate by URL across all sources.
  3. Enrich with Gemini (batched) using profile/context.md + learned feedback.
  4. Push to Notion, deduplicating by URL again before every write.

Run:  python -m scraper.main
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from scraper.filters import is_us_location, load_config, load_personas
from scraper.sources import aggregators, company_boards, linkedin, niche_boards
from storage.notion_sync import sync

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Each source is isolated by its own try/except below.
SOURCES = [
    ("Company Boards", company_boards.fetch),
    ("Aggregators", aggregators.fetch),
    ("Niche Boards", niche_boards.fetch),
    ("LinkedIn", linkedin.fetch),
]


def ai_enabled(config: dict) -> bool:
    if not (config.get("ai", {}) or {}).get("enabled", True):
        return False
    return bool(os.environ.get("GEMINI_API_KEY"))


def main() -> None:
    config = load_config()
    provider = config.get("storage", {}).get("provider", "notion")

    if provider == "notion":
        db_id = os.environ.get("NOTION_DATABASE_ID")
        if not db_id:
            print("ERROR: NOTION_DATABASE_ID not set (run setup.py first)")
            sys.exit(1)
    else:
        print(f"ERROR: storage provider '{provider}' not wired in main.py")
        sys.exit(1)

    # ---- COLLECT ----
    all_items: list[dict] = []
    for name, fetch_fn in SOURCES:
        print(f"[{name}] fetching...")
        try:
            got = fetch_fn()
            print(f"[{name}] -> {len(got)} items")
            all_items.extend(got)
        except Exception as e:  # belt-and-suspenders; sources also self-isolate
            print(f"[{name}] FAILED: {e}")

    # ---- DEDUPE (by URL, across all sources) ----
    seen, deduped = set(), []
    for item in all_items:
        url = (item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(item)
    print(f"\nUnique items after dedupe: {len(deduped)}")

    # ---- LOCATION FILTER (filters.us_only) ----
    if (config.get("filters", {}) or {}).get("us_only"):
        before = len(deduped)
        deduped = [it for it in deduped if is_us_location(it.get("location", ""))]
        dropped = before - len(deduped)
        if dropped:
            print(f"[location] dropped {dropped} non-US roles (us_only) — {len(deduped)} remain")

    # ---- ENRICH ----
    ai_on = ai_enabled(config)
    if ai_on and deduped:
        from ai.memory import build_preference_prompt, load_feedback
        from ai.pipeline import analyse_batch

        preference = build_preference_prompt(load_feedback())
        personas = load_personas()
        deduped = analyse_batch(deduped, personas, preference_prompt=preference)
    elif not ai_on:
        print("[AI] Skipped — disabled in config or GEMINI_API_KEY not set")
    else:
        print("[AI] No items to score")

    # ---- STORE ----
    added, skipped = sync(db_id, deduped)
    print(f"\nDone — {added} new, {skipped} existing/failed")


if __name__ == "__main__":
    main()
