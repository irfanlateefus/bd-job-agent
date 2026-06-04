"""
LinkedIn Jobs — Playwright, conservative rate limiting, fully isolated.

LinkedIn aggressively blocks automation. This source is wrapped end-to-end so a
block, timeout, or layout change is logged and yields [] — it can never break
the other sources. Uses the public guest jobs search (no login). Be gentle:
few actions, real pauses, small result cap. All knobs live in config.yaml.
"""
from datetime import datetime, timezone
from urllib.parse import quote, urlparse, urlunparse

from bs4 import BeautifulSoup

from scraper.filters import is_relevant, load_config

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _clean_url(url: str) -> str:
    try:
        p = urlparse(url)
        return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
    except ValueError:
        return url


def fetch() -> list[dict]:
    cfg = load_config().get("linkedin", {}) or {}
    if not cfg.get("enabled", True):
        print("  [LinkedIn] disabled in config")
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [LinkedIn] playwright not installed — skipped")
        return []

    keywords = cfg.get("keywords", "business development")
    location = cfg.get("location", "United States")
    max_results = int(cfg.get("max_results", 25))
    pause_ms = int(float(cfg.get("rate_limit_seconds", 4.0)) * 1000)
    # f_TPR=r604800 → posted in the last 7 days
    url = (f"https://www.linkedin.com/jobs/search?keywords={quote(keywords)}"
           f"&location={quote(location)}&f_TPR=r604800")

    items: list[dict] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_context(user_agent=UA, locale="en-US").new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(pause_ms)
                for _ in range(2):  # conservative: at most two lazy-load scrolls
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(pause_ms)
                html = page.content()
            finally:
                browser.close()

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.base-card, li") or []
        for card in cards:
            title_el = card.select_one("h3")
            link_el = card.select_one("a.base-card__full-link") or card.select_one("a[href*='/jobs/view/']")
            company_el = card.select_one("h4")
            if not (title_el and link_el):
                continue
            title = title_el.get_text(strip=True)
            if not is_relevant(title):
                continue
            items.append({
                "name": title,
                "company": company_el.get_text(strip=True) if company_el else "",
                "url": _clean_url(link_el.get("href", "")),
                "source": "LinkedIn",
                "date_found": _today(),
                "location": location,
            })
            if len(items) >= max_results:
                break
    except Exception as e:  # any block/timeout/layout change — stay isolated
        msg = str(e)
        if "Executable doesn't exist" in msg or "playwright install" in msg:
            print("  [LinkedIn] Chromium not installed — run: python -m playwright install chromium")
        else:
            print(f"  [LinkedIn] blocked/failed (isolated): {e}")
        return items
    return items
