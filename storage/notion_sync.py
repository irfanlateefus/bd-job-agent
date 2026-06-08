"""
Notion storage. Deduplicates by URL before every write. Maps the standard item
schema to the database properties:
  Name (title) | Company | URL | Source | AI Score | Summary | Notes |
  Date Found | Status
"""
import os

from notion_client import Client
from notion_client.errors import APIResponseError

_client = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(auth=os.environ["NOTION_TOKEN"])
    return _client


def _norm_url(url) -> str:
    """Normalize a URL for both storage and dedup so the written value and the
    dedup key can never diverge (e.g. RSS <link> text with stray whitespace)."""
    return (url or "").strip()


def get_existing_urls(db_id: str) -> set[str]:
    """All URLs already in the database — used for deduplication."""
    client, seen, cursor = get_client(), set(), None
    while True:
        kwargs = {"database_id": db_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = client.databases.query(**kwargs)
        for page in resp["results"]:
            url = _norm_url(page["properties"].get("URL", {}).get("url", ""))
            if url:
                seen.add(url)
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return seen


def _rich_text(value: str) -> dict:
    return {"rich_text": [{"text": {"content": (value or "")[:2000]}}]}


def build_properties(item: dict) -> dict:
    props = {
        "Name": {"title": [{"text": {"content": (item.get("name") or "")[:200]}}]},
        "URL": {"url": _norm_url(item.get("url")) or None},
        "Source": {"select": {"name": item.get("source", "Unknown")}},
        "Status": {"select": {"name": "New"}},
    }
    if item.get("company"):
        props["Company"] = _rich_text(item["company"])
    if item.get("persona"):
        props["Persona"] = {"select": {"name": item["persona"]}}
    if item.get("date_found"):
        props["Date Found"] = {"date": {"start": item["date_found"]}}
    if item.get("ai_score") is not None:
        props["AI Score"] = {"number": item["ai_score"]}
    if item.get("ai_summary"):
        props["Summary"] = _rich_text(item["ai_summary"])
    if item.get("ai_notes"):
        props["Notes"] = _rich_text(item["ai_notes"])
    return props


def push_item(db_id: str, item: dict) -> bool:
    try:
        get_client().pages.create(parent={"database_id": db_id}, properties=build_properties(item))
        return True
    except APIResponseError as e:
        print(f"[notion] push failed for {item.get('url', '?')}: {e}")
        return False


def sync(db_id: str, items: list[dict]) -> tuple[int, int]:
    """Push new items, skipping any URL already stored. Returns (added, skipped)."""
    existing = get_existing_urls(db_id)
    added = skipped = 0
    for item in items:
        url = _norm_url(item.get("url"))
        if not url or url in existing:
            skipped += 1
            continue
        if push_item(db_id, item):
            added += 1
            existing.add(url)
        else:
            skipped += 1
    return added, skipped
