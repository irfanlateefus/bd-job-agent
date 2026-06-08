"""
Set up the Notion database for the agent — idempotent, safe to re-run.

- If a database titled "BD Job Pipeline" is already visible to your integration,
  it adds any MISSING properties and leaves the rest alone (repairs a half-set-up
  or manually-created database).
- Otherwise it creates the database under NOTION_PARENT_PAGE_ID.

Either way it prints the NOTION_DATABASE_ID to put in .env and your GitHub secret.

Prereqs:
  - NOTION_TOKEN          (your integration's Internal Integration Secret)
  - NOTION_PARENT_PAGE_ID (only needed when creating a brand-new database)

Run:  python setup.py
"""
import logging
import os
import sys

from dotenv import load_dotenv
from notion_client import Client
from notion_client.errors import APIErrorCode, APIResponseError

load_dotenv()

DB_TITLE = "BD Job Pipeline"

SOURCE_OPTIONS = [
    {"name": "Greenhouse", "color": "green"},
    {"name": "Lever", "color": "blue"},
    {"name": "Ashby", "color": "purple"},
    {"name": "RemoteOK", "color": "orange"},
    {"name": "Indeed", "color": "yellow"},
    {"name": "HN Who's Hiring", "color": "red"},
    {"name": "LinkedIn", "color": "blue"},
    {"name": "WeWorkRemotely", "color": "pink"},
    {"name": "RepVue", "color": "brown"},
    {"name": "Wellfound", "color": "gray"},
    {"name": "Unknown", "color": "default"},
]

STATUS_OPTIONS = [
    {"name": "New", "color": "gray"},
    {"name": "Interested", "color": "blue"},
    {"name": "Applied", "color": "green"},
    {"name": "Skip", "color": "yellow"},
    {"name": "Rejected", "color": "red"},
]

PERSONA_OPTIONS = [
    {"name": "Business Development", "color": "blue"},
    {"name": "Solution Architect", "color": "green"},
]

# Single source of truth for the schema — used for both create and repair.
PROPERTIES = {
    "Name": {"title": {}},
    "Company": {"rich_text": {}},
    "Persona": {"select": {"options": PERSONA_OPTIONS}},
    "URL": {"url": {}},
    "Source": {"select": {"options": SOURCE_OPTIONS}},
    "AI Score": {"number": {"format": "number"}},
    "Summary": {"rich_text": {}},
    "Notes": {"rich_text": {}},
    "Date Found": {"date": {}},
    "Status": {"select": {"options": STATUS_OPTIONS}},
}


def _explain(e: APIResponseError) -> None:
    """Print a clean, actionable message for the common Notion setup errors."""
    code = getattr(e, "code", None)
    if code == APIErrorCode.Unauthorized:
        print("\nERROR: Notion rejected your NOTION_TOKEN (401 — invalid token).")
        print("  - Copy the *Internal Integration Secret* from "
              "https://www.notion.so/my-integrations (starts with 'ntn_' or 'secret_').")
        print("  - In .env it must be exactly  NOTION_TOKEN=ntn_...  (no quotes, no spaces).")
    elif code in (APIErrorCode.ObjectNotFound, APIErrorCode.RestrictedResource):
        print("\nERROR: Notion can't access the parent page.")
        print("  - Check NOTION_PARENT_PAGE_ID is the 32-char id from the page URL.")
        print("  - Open that page -> Share -> Connections -> add your integration.")
    elif code == APIErrorCode.ValidationError:
        print(f"\nERROR: Notion rejected the request (validation): {e}")
        print("  - Usually a malformed NOTION_PARENT_PAGE_ID — re-copy it from the page URL.")
    else:
        print(f"\nERROR: Notion API error [{code}]: {e}")


def _find_existing(client: Client) -> dict | None:
    """Return a database titled DB_TITLE that the integration can see, or None."""
    resp = client.search(filter={"value": "database", "property": "object"})
    matches = [
        db for db in resp.get("results", [])
        if "".join(t.get("plain_text", "") for t in db.get("title", [])) == DB_TITLE
    ]
    if len(matches) > 1:
        print(f"WARNING: {len(matches)} databases named '{DB_TITLE}' found — using the first.")
    return matches[0] if matches else None


def _ensure_schema(client: Client, db: dict) -> list:
    """Add any missing properties to an existing database. Returns names added."""
    existing = set(db.get("properties", {}).keys())
    missing = {k: v for k, v in PROPERTIES.items() if k != "Name" and k not in existing}
    if missing:
        client.databases.update(database_id=db["id"], properties=missing)
    return list(missing.keys())


def main() -> None:
    token = (os.environ.get("NOTION_TOKEN") or "").strip()
    if not token:
        print("ERROR: set NOTION_TOKEN in .env first (copy .env.example to .env and fill it in).")
        sys.exit(1)
    if not token.startswith(("ntn_", "secret_")):
        print("WARNING: NOTION_TOKEN doesn't look like an integration secret "
              "(expected a 'ntn_' or 'secret_' prefix). Copy the Internal Integration "
              "Secret from https://www.notion.so/my-integrations — not a page id.\n")

    # log_level quiets notion-client's own WARNING log so only our message shows.
    client = Client(auth=token, log_level=logging.ERROR)
    try:
        existing = _find_existing(client)
        if existing:
            db_id = existing["id"]
            added = _ensure_schema(client, existing)
            if added:
                print(f"Found existing '{DB_TITLE}' — added missing properties: {', '.join(added)}.")
            else:
                print(f"Found existing '{DB_TITLE}' — schema already complete.")
        else:
            parent = (os.environ.get("NOTION_PARENT_PAGE_ID") or "").strip()
            if not parent:
                print("ERROR: no existing 'BD Job Pipeline' database is visible to your "
                      "integration, and NOTION_PARENT_PAGE_ID is not set.")
                print("  - Set NOTION_PARENT_PAGE_ID in .env (a page shared with the "
                      "integration) so the database can be created there.")
                sys.exit(1)
            db = client.databases.create(
                parent={"type": "page_id", "page_id": parent},
                title=[{"type": "text", "text": {"content": DB_TITLE}}],
                properties=PROPERTIES,
            )
            db_id = db["id"]
            print(f"Created '{DB_TITLE}'.")
    except APIResponseError as e:
        _explain(e)
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: could not reach Notion ({type(e).__name__}). "
              "Check your network connection and try again.")
        sys.exit(1)

    print(f"\n  NOTION_DATABASE_ID={db_id}\n")
    print("Put that in .env and set it as a GitHub secret:")
    print("  gh secret set NOTION_DATABASE_ID --repo irfanlateefus/bd-job-agent")


if __name__ == "__main__":
    main()
