"""
Preflight — verify all three credentials before a real run.

Checks GEMINI_API_KEY (live call), NOTION_TOKEN (auth), and NOTION_DATABASE_ID
(readable by the integration). Prints a clean PASS/FAIL line for each and never
prints secret values.

Run:  python preflight.py
"""
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

NV = "2022-06-28"  # Notion API version


def check_gemini() -> bool:
    k = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not k:
        print("[FAIL] GEMINI_API_KEY — not set in .env (get one at https://aistudio.google.com/apikey)")
        return False
    try:
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.0-flash-lite:generateContent",
            headers={"x-goog-api-key": k, "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": "ok"}]}]},
            timeout=20,
        )
    except requests.RequestException as e:
        print(f"[FAIL] GEMINI_API_KEY — network error: {type(e).__name__}")
        return False
    if r.status_code == 200:
        print(f"[PASS] GEMINI_API_KEY — key works (prefix {k[:4]}...)")
        return True
    try:
        msg = r.json().get("error", {}).get("message", "")
    except ValueError:
        msg = r.text[:120]
    print(f"[FAIL] GEMINI_API_KEY — HTTP {r.status_code}: {msg or 'rejected'}")
    return False


def _notion_get(path: str, token: str) -> requests.Response:
    return requests.get(
        f"https://api.notion.com/v1/{path}",
        headers={"Authorization": f"Bearer {token}", "Notion-Version": NV},
        timeout=20,
    )


def check_notion() -> bool:
    token = (os.environ.get("NOTION_TOKEN") or "").strip()
    db = (os.environ.get("NOTION_DATABASE_ID") or "").strip()

    if not token:
        print("[FAIL] NOTION_TOKEN — not set in .env (Internal Integration Secret, starts with ntn_)")
        return False
    try:
        me = _notion_get("users/me", token)
    except requests.RequestException as e:
        print(f"[FAIL] NOTION_TOKEN — network error: {type(e).__name__}")
        return False
    if me.status_code != 200:
        print(f"[FAIL] NOTION_TOKEN — HTTP {me.status_code}: {me.json().get('message', 'invalid token')}")
        return False
    print(f"[PASS] NOTION_TOKEN — valid (integration: {me.json().get('name', '?')})")

    if not db:
        print("[FAIL] NOTION_DATABASE_ID — not set in .env (run `python setup.py`, then add its output)")
        return False
    d = _notion_get(f"databases/{db}", token)
    if d.status_code == 200:
        title = "".join(t.get("plain_text", "") for t in d.json().get("title", [])) or "(untitled)"
        print(f"[PASS] NOTION_DATABASE_ID — readable (database: {title})")
        return True
    hint = "share the database with your integration, or re-copy the id" if d.status_code == 404 else ""
    print(f"[FAIL] NOTION_DATABASE_ID — HTTP {d.status_code}: {d.json().get('message', 'not accessible')}"
          + (f" ({hint})" if hint else ""))
    return False


def main() -> None:
    print("Preflight — checking credentials...\n")
    gemini_ok = check_gemini()
    notion_ok = check_notion()
    print()
    if gemini_ok and notion_ok:
        print("All checks passed. Next:  python -m scraper.main")
        sys.exit(0)
    print("Fix the FAIL item(s) above, then re-run:  python preflight.py")
    sys.exit(1)


if __name__ == "__main__":
    main()
