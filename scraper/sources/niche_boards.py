"""
Niche boards — config-driven, dispatched by `method` (rss | html | playwright).

Each board in the `niche_boards` list of config.yaml is isolated: one board
failing (bad selector, anti-bot, missing Playwright) is logged and skipped,
never breaking the others. Per-board counts are logged every run.
"""
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scraper.filters import is_relevant, load_config

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; bd-job-agent/1.0; research)"}
TIMEOUT = 25
MAX_HTML_ITEMS = 50


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _rss(url: str, board: str) -> list[dict]:
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    items = []
    for it in root.findall(".//item"):
        title = (it.findtext("title", "") or "").strip()
        if not is_relevant(title):
            continue
        # Many job RSS titles are "Company: Role" or "Role at Company"
        company, name = "", title
        if ":" in title:
            company, name = (s.strip() for s in title.split(":", 1))
        elif " at " in title:
            name, company = (s.strip() for s in title.rsplit(" at ", 1))
        items.append({
            "name": name,
            "company": company,
            "url": (it.findtext("link", "") or "").strip(),
            "source": board,
            "date_found": _today(),
        })
    return items


def _extract_anchors(html: str, base_url: str, board: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    seen, items = set(), []
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if not text or len(text) < 4 or not is_relevant(text):
            continue
        href = urljoin(base_url, a["href"])
        if not href.startswith("http") or href in seen:
            continue
        seen.add(href)
        items.append({
            "name": text[:140],
            "company": "",
            "url": href,
            "source": board,
            "date_found": _today(),
        })
        if len(items) >= MAX_HTML_ITEMS:
            break
    return items


def _html(url: str, board: str) -> list[dict]:
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return _extract_anchors(resp.text, url, board)


def _playwright(url: str, board: str) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"    [{board}] playwright not installed — skipped")
        return []
    html = ""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_context(user_agent=HEADERS["User-Agent"]).new_page()
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            html = page.content()
        finally:
            browser.close()
    return _extract_anchors(html, url, board)


_DISPATCH = {"rss": _rss, "html": _html, "playwright": _playwright}


def fetch() -> list[dict]:
    """Fetch BD-relevant listings from every configured niche board."""
    boards = load_config().get("niche_boards", []) or []
    items: list[dict] = []
    for b in boards:
        name = b.get("name", "board")
        method = (b.get("method") or "").lower()
        url = b.get("url", "")
        runner = _DISPATCH.get(method)
        if not runner:
            print(f"  [{name}] unknown method '{method}' — skipped")
            continue
        try:
            got = runner(url, name)
            items.extend(got)
            print(f"  [{name}] {method} — {len(got)} BD-relevant items")
        except Exception as e:  # isolate each board
            print(f"  [{name}] FAILED ({method}, isolated): {e}")
    return items
