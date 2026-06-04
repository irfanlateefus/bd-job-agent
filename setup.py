"""
One-time Notion schema creation.

Creates the database with all properties the agent expects, then prints the new
database id. Copy that id into NOTION_DATABASE_ID (.env locally, or the GitHub
secret).

Prereqs:
  - NOTION_TOKEN          (your integration token)
  - NOTION_PARENT_PAGE_ID (a page the integration can edit; the DB lands here)

Run:  python setup.py
"""
import logging
import os
import sys

from dotenv import load_dotenv
from notion_client import Client
from notion_client.errors import APIErrorCode, APIResponseError

load_dotenv()

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


def main() -> None:
    token = (os.environ.get("NOTION_TOKEN") or "").strip()
    parent = (os.environ.get("NOTION_PARENT_PAGE_ID") or "").strip()
    if not token or not parent:
        print("ERROR: set NOTION_TOKEN and NOTION_PARENT_PAGE_ID in .env first "
              "(copy .env.example to .env and fill both in).")
        sys.exit(1)
    if not token.startswith(("ntn_", "secret_")):
        print("WARNING: NOTION_TOKEN doesn't look like an integration secret "
              "(expected a 'ntn_' or 'secret_' prefix). Copy the Internal Integration "
              "Secret from https://www.notion.so/my-integrations — not a page id.\n")

    # log_level quiets notion-client's own WARNING log so only our message shows.
    client = Client(auth=token, log_level=logging.ERROR)
    try:
        db = client.databases.create(
            parent={"type": "page_id", "page_id": parent},
            title=[{"type": "text", "text": {"content": "BD Job Pipeline"}}],
            properties={
                "Name": {"title": {}},
                "Company": {"rich_text": {}},
                "URL": {"url": {}},
                "Source": {"select": {"options": SOURCE_OPTIONS}},
                "AI Score": {"number": {"format": "number"}},
                "Summary": {"rich_text": {}},
                "Notes": {"rich_text": {}},
                "Date Found": {"date": {}},
                "Status": {"select": {"options": STATUS_OPTIONS}},
            },
        )
    except APIResponseError as e:
        _explain(e)
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: could not reach Notion ({type(e).__name__}). "
              "Check your network connection and try again.")
        sys.exit(1)

    print("Database created successfully.")
    print(f"\n  NOTION_DATABASE_ID={db['id']}\n")
    print("Next: set it as a GitHub Actions secret, e.g.")
    print("  gh secret set NOTION_DATABASE_ID --repo irfanlateefus/bd-job-agent")


if __name__ == "__main__":
    main()
