"""
Sync learning feedback from Notion into data/feedback.json.

Reads the database, buckets each row by its Status:
  positive_statuses (Applied/Interested)  -> positive examples
  negative_statuses (Skip/Rejected)       -> negative examples
and writes "Company — Role" patterns the scoring prompt replays on the next run.

The GitHub Actions workflow runs this and commits data/feedback.json so the
agent gets smarter over time.

Run:  python feedback_sync.py
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from ai.memory import save_feedback
from scraper.filters import load_config
from storage.notion_sync import get_client

MAX_EXAMPLES = 50


def _title(props: dict) -> str:
    rich = props.get("Name", {}).get("title", [])
    return rich[0]["plain_text"] if rich else ""


def _rich(props: dict, key: str) -> str:
    rich = props.get(key, {}).get("rich_text", [])
    return rich[0]["plain_text"] if rich else ""


def _status(props: dict) -> str:
    sel = props.get("Status", {}).get("select")
    return sel["name"] if sel else ""


def main() -> None:
    db_id = os.environ.get("NOTION_DATABASE_ID")
    if not db_id:
        print("ERROR: NOTION_DATABASE_ID not set")
        sys.exit(1)

    fb_cfg = load_config().get("feedback", {}) or {}
    positive_statuses = set(fb_cfg.get("positive_statuses", []))
    negative_statuses = set(fb_cfg.get("negative_statuses", []))

    client, cursor = get_client(), None
    positive, negative = [], []
    while True:
        kwargs = {"database_id": db_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = client.databases.query(**kwargs)
        for page in resp["results"]:
            props = page["properties"]
            status = _status(props)
            label = f"{_rich(props, 'Company') or '?'} — {_title(props)}".strip()
            if not label or label == "? — ":
                continue
            if status in positive_statuses:
                positive.append(label)
            elif status in negative_statuses:
                negative.append(label)
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")

    # de-dupe, keep most recent
    positive = list(dict.fromkeys(positive))[-MAX_EXAMPLES:]
    negative = list(dict.fromkeys(negative))[-MAX_EXAMPLES:]
    save_feedback({"positive": positive, "negative": negative})
    print(f"Feedback updated — {len(positive)} positive, {len(negative)} negative")


if __name__ == "__main__":
    main()
