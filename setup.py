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
import os
import sys

from dotenv import load_dotenv
from notion_client import Client

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


def main() -> None:
    token = os.environ.get("NOTION_TOKEN")
    parent = os.environ.get("NOTION_PARENT_PAGE_ID")
    if not token or not parent:
        print("ERROR: set NOTION_TOKEN and NOTION_PARENT_PAGE_ID in .env first")
        sys.exit(1)

    client = Client(auth=token)
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
    print("Database created successfully.")
    print(f"\n  NOTION_DATABASE_ID={db['id']}\n")
    print("Set that value in your .env and as a GitHub Actions secret.")


if __name__ == "__main__":
    main()
