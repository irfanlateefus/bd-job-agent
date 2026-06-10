"""
One-time cleanup: mark existing non-US rows as Skip.

The agent now filters non-US roles going forward (filters.us_only), but rows
stored before that need cleaning. This re-derives each row's location by
re-fetching the company boards (which carry clean locations) and falling back to
a title heuristic, then sets clearly-non-US rows that are still 'New' to
Status=Skip so they drop out of the active queue.

Re-runnable. Never touches Applied / Interested / already-Skipped rows.

Run:  python cleanup_non_us.py
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from notion_client.errors import APIResponseError

from scraper.filters import is_us_location
from scraper.sources import company_boards
from storage.notion_sync import _norm_url, _rich_text, get_client


def main() -> None:
    db = os.environ.get("NOTION_DATABASE_ID")
    if not db:
        print("ERROR: NOTION_DATABASE_ID not set")
        sys.exit(1)
    client = get_client()

    print("Building location map from company boards (reliable locations)...")
    loc_map: dict = {}
    for it in company_boards.fetch():
        u = _norm_url(it.get("url"))
        if u:
            loc_map[u] = it.get("location", "")
    print(f"  {len(loc_map)} company-board roles mapped\n")

    cursor = None
    checked = skipped = failed = 0
    while True:
        kwargs = {"database_id": db, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = client.databases.query(**kwargs)
        for p in resp["results"]:
            pr = p["properties"]
            status = (pr.get("Status", {}).get("select") or {}).get("name", "")
            if status in ("Applied", "Interested", "Skip", "Rejected"):
                continue  # leave pursued / already-handled rows alone
            checked += 1
            t = pr["Name"]["title"]
            name = t[0]["plain_text"] if t else ""
            url = _norm_url(pr.get("URL", {}).get("url", ""))
            loc = loc_map.get(url)
            if loc is not None:
                us, src = is_us_location(loc), (loc or "(blank)")
            else:
                us, src = is_us_location(name), "(from title)"
            if not us:
                props = {"Status": {"select": {"name": "Skip"}}}
                if loc:
                    props["Location"] = _rich_text(loc)
                try:
                    client.pages.update(page_id=p["id"], properties=props)
                    skipped += 1
                    print(f"  SKIP non-US: {name[:50]:52} [{src}]")
                except APIResponseError as e:
                    failed += 1
                    print(f"  update failed for {name[:40]}: {e}")
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")

    print(f"\nDone — checked {checked} active rows, marked {skipped} non-US as Skip"
          + (f", {failed} failed." if failed else "."))


if __name__ == "__main__":
    main()
