"""
Backfill AI scores on rows that don't have one yet.

Useful after you add the GEMINI_API_KEY, change the profile, or import rows from
elsewhere. Queries Notion for pages missing an AI Score, scores them in batches,
and updates each page in place.

Run:  python enrich_existing.py
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from notion_client.errors import APIResponseError

from ai.memory import build_preference_prompt, load_feedback
from ai.pipeline import analyse_batch
from scraper.filters import load_personas
from storage.notion_sync import _rich_text, get_client

PROJECT_ROOT = Path(__file__).resolve().parent


def _title(props: dict) -> str:
    rich = props.get("Name", {}).get("title", [])
    return rich[0]["plain_text"] if rich else ""


def _rich(props: dict, key: str) -> str:
    rich = props.get(key, {}).get("rich_text", [])
    return rich[0]["plain_text"] if rich else ""


def main() -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY not set")
        sys.exit(1)
    db_id = os.environ.get("NOTION_DATABASE_ID")
    if not db_id:
        print("ERROR: NOTION_DATABASE_ID not set")
        sys.exit(1)

    client, cursor, todo = get_client(), None, []
    while True:
        kwargs = {"database_id": db_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = client.databases.query(**kwargs)
        for page in resp["results"]:
            props = page["properties"]
            if props.get("AI Score", {}).get("number") is not None:
                continue
            todo.append({
                "_page_id": page["id"],
                "name": _title(props),
                "company": _rich(props, "Company"),
                "url": props.get("URL", {}).get("url", ""),
                "source": (props.get("Source", {}).get("select") or {}).get("name", ""),
            })
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")

    if not todo:
        print("Nothing to enrich — all rows already scored.")
        return

    print(f"Enriching {len(todo)} rows...")
    preference = build_preference_prompt(load_feedback())
    personas = load_personas()
    enriched = analyse_batch(todo, personas, preference_prompt=preference)

    updated = 0
    for item in enriched:
        if item.get("ai_score") is None:
            continue
        props = {"AI Score": {"number": item["ai_score"]}}
        if item.get("persona"):
            props["Persona"] = {"select": {"name": item["persona"]}}
        if item.get("ai_summary"):
            props["Summary"] = _rich_text(item["ai_summary"])
        if item.get("ai_notes"):
            props["Notes"] = _rich_text(item["ai_notes"])
        try:
            client.pages.update(page_id=item["_page_id"], properties=props)
            updated += 1
        except APIResponseError as e:
            print(f"[enrich] update failed for {item['_page_id']}: {e}")
    print(f"Done — updated {updated} rows.")


if __name__ == "__main__":
    main()
