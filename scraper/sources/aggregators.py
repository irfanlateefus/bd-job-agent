"""
Aggregators — RemoteOK (JSON API), Indeed (RSS), and Hacker News
"Who is hiring?" (HN Algolia + Firebase APIs).

Each aggregator is wrapped so one failure (Indeed loves to 403 bots, RemoteOK
sometimes rate-limits) never breaks the others. Per-aggregator counts logged.
"""
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from scraper.filters import is_relevant, load_config

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; bd-job-agent/1.0; research)"}
TIMEOUT = 20
_HREF = re.compile(r'href="(https?://[^"]+)"', re.IGNORECASE)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _strip_html(html: str) -> str:
    return BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)


# ---- RemoteOK ---------------------------------------------------------------

def _remoteok() -> list[dict]:
    resp = requests.get("https://remoteok.com/api", headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    items = []
    for j in data:
        if not isinstance(j, dict) or not j.get("position"):
            continue  # first element is a legal/metadata notice
        title = j.get("position", "")
        if not is_relevant(title):
            continue
        items.append({
            "name": title,
            "company": j.get("company", ""),
            "url": j.get("url", ""),
            "source": "RemoteOK",
            "date_found": _today(),
            "location": j.get("location", "Remote") or "Remote",
            "description": _strip_html(j.get("description", ""))[:300],
        })
    return items


# ---- Indeed (RSS) -----------------------------------------------------------

def _indeed(cfg: dict) -> list[dict]:
    queries = cfg.get("queries", []) or []
    location = cfg.get("location", "Remote")
    items: list[dict] = []
    for q in queries:
        url = f"https://www.indeed.com/rss?q={quote(q)}&l={quote(location)}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code != 200:
                print(f"    [indeed:{q}] HTTP {resp.status_code} — skipped")
                continue
            root = ET.fromstring(resp.text)
        except (requests.RequestException, ET.ParseError) as e:
            print(f"    [indeed:{q}] failed — {e}")
            continue
        for it in root.findall(".//item"):
            title = it.findtext("title", "") or ""
            if not is_relevant(title):
                continue
            # Indeed titles are usually "Role - Company - Location"
            parts = [p.strip() for p in title.split(" - ")]
            company = parts[1] if len(parts) >= 2 else ""
            items.append({
                "name": parts[0] if parts else title,
                "company": company,
                "url": it.findtext("link", "") or "",
                "source": "Indeed",
                "date_found": _today(),
                "location": location,
            })
    return items


# ---- Hacker News "Who is hiring?" ------------------------------------------

def _hn(cfg: dict) -> list[dict]:
    max_comments = int(cfg.get("max_comments", 80))
    # 1) find the most recent "Who is hiring?" thread by the whoishiring account
    search = requests.get(
        "https://hn.algolia.com/api/v1/search_by_date",
        params={"tags": "story,author_whoishiring", "query": "who is hiring", "hitsPerPage": 5},
        headers=HEADERS, timeout=TIMEOUT,
    )
    search.raise_for_status()
    hits = search.json().get("hits", [])
    thread = next((h for h in hits if "who is hiring" in (h.get("title", "") or "").lower()), None)
    if not thread:
        print("    [hackernews] no active 'Who is hiring?' thread found")
        return []
    thread_id = thread.get("objectID")
    story = requests.get(
        f"https://hacker-news.firebaseio.com/v0/item/{thread_id}.json",
        headers=HEADERS, timeout=TIMEOUT,
    ).json() or {}
    kids = (story.get("kids") or [])[:max_comments]

    items = []
    for cid in kids:
        try:
            c = requests.get(
                f"https://hacker-news.firebaseio.com/v0/item/{cid}.json",
                headers=HEADERS, timeout=15,
            ).json() or {}
        except requests.RequestException:
            continue
        raw = c.get("text")
        if not raw or c.get("deleted") or c.get("dead"):
            continue
        # HN job comments lead with a structured header ("Company | Role |
        # Location | ...") before the first <p> paragraph. Match on that header
        # so we don't false-positive on keywords buried in the description prose.
        header = _strip_html(raw.split("<p>")[0])
        if not is_relevant(header):
            continue
        text = _strip_html(raw)
        parts = [p.strip() for p in header.split("|")]
        company = parts[0][:80] if parts else ""
        link_match = _HREF.search(raw)
        url = link_match.group(1) if link_match else f"https://news.ycombinator.com/item?id={cid}"
        items.append({
            "name": header[:120],
            "company": company,
            "url": url,
            "source": "HN Who's Hiring",
            "date_found": _today(),
            "description": text[:300],
        })
        time.sleep(0.05)  # be gentle to the firebase API
    return items


def fetch() -> list[dict]:
    """Fetch BD-relevant listings from every enabled aggregator."""
    cfg = load_config().get("aggregators", {}) or {}
    items: list[dict] = []

    runners = [
        ("RemoteOK", cfg.get("remoteok", {}), lambda c: _remoteok()),
        ("Indeed", cfg.get("indeed", {}), _indeed),
        ("HackerNews", cfg.get("hackernews", {}), _hn),
    ]
    for label, sub, runner in runners:
        if not (sub or {}).get("enabled", True):
            print(f"  [{label}] disabled in config")
            continue
        try:
            got = runner(sub or {})
            items.extend(got)
            print(f"  [{label}] {len(got)} BD-relevant items")
        except Exception as e:  # isolate each aggregator
            print(f"  [{label}] FAILED (isolated): {e}")
    return items
