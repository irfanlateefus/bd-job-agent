"""
Company boards — Greenhouse, Lever, and Ashby public JSON APIs.

Iterates the `companies` block in config.yaml (one slug per line). Each slug is
isolated: a dead/renamed slug or network blip is logged and skipped, never
breaking the others. Per-slug counts and HTTP status are logged every run, which
doubles as the "validate board URLs" requirement (see validate_sources.py for a
standalone summary).

Endpoints:
  Greenhouse: https://boards-api.greenhouse.io/v1/boards/<slug>/jobs
  Lever:      https://api.lever.co/v0/postings/<slug>?mode=json
  Ashby:      https://api.ashbyhq.com/posting-api/job-board/<slug>
"""
from datetime import datetime, timezone

import requests

from scraper.filters import is_relevant, load_config

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; bd-job-agent/1.0; research)"}
TIMEOUT = 20


class SlugNotFound(Exception):
    """Raised when a board slug returns 404 (dead or renamed)."""


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _company_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _get(url: str) -> requests.Response:
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    if resp.status_code == 404:
        raise SlugNotFound()
    resp.raise_for_status()
    return resp


# ---- per-ATS fetchers: return (relevant_items, total_jobs_seen) -------------

def _greenhouse(slug: str) -> tuple[list[dict], int]:
    data = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs").json()
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    items = []
    for j in jobs:
        title = j.get("title", "")
        if not is_relevant(title):
            continue
        items.append({
            "name": title,
            "company": _company_from_slug(slug),
            "url": j.get("absolute_url", ""),
            "source": "Greenhouse",
            "date_found": _today(),
            "location": (j.get("location") or {}).get("name", ""),
        })
    return items, len(jobs)


def _lever(slug: str) -> tuple[list[dict], int]:
    data = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json").json()
    postings = data if isinstance(data, list) else []
    items = []
    for p in postings:
        title = p.get("text", "")
        if not is_relevant(title):
            continue
        cats = p.get("categories") or {}
        items.append({
            "name": title,
            "company": _company_from_slug(slug),
            "url": p.get("hostedUrl", ""),
            "source": "Lever",
            "date_found": _today(),
            "location": cats.get("location", ""),
            "description": (p.get("descriptionPlain", "") or "")[:300],
        })
    return items, len(postings)


def _ashby(slug: str) -> tuple[list[dict], int]:
    data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}").json()
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    items = []
    for j in jobs:
        if j.get("isListed") is False:
            continue
        title = j.get("title", "")
        if not is_relevant(title):
            continue
        items.append({
            "name": title,
            "company": _company_from_slug(slug),
            "url": j.get("jobUrl") or j.get("applyUrl") or "",
            "source": "Ashby",
            "date_found": _today(),
            "location": j.get("location", ""),
        })
    return items, len(jobs)


_FETCHERS = (("greenhouse", _greenhouse), ("lever", _lever), ("ashby", _ashby))


def fetch() -> list[dict]:
    """Fetch BD-relevant listings across every configured company board."""
    companies = load_config().get("companies", {}) or {}
    items: list[dict] = []
    print("  [company-boards] validating + scraping slugs:")
    for ats, fetcher in _FETCHERS:
        for slug in companies.get(ats, []) or []:
            try:
                board_items, total = fetcher(slug)
                items.extend(board_items)
                print(f"    [{ats}:{slug}] OK — {total} jobs, {len(board_items)} BD-relevant")
            except SlugNotFound:
                print(f"    [{ats}:{slug}] 404 — dead slug, SKIPPED (fix in config.yaml)")
            except requests.RequestException as e:
                print(f"    [{ats}:{slug}] ERROR — {e}")
            except Exception as e:  # never let one board break the source
                print(f"    [{ats}:{slug}] ERROR — {e}")
    return items


def validate() -> list[dict]:
    """
    Check every configured slug without applying the relevance filter.
    Returns one row per slug for validate_sources.py to summarise.
    """
    companies = load_config().get("companies", {}) or {}
    rows: list[dict] = []
    for ats, fetcher in _FETCHERS:
        for slug in companies.get(ats, []) or []:
            try:
                board_items, total = fetcher(slug)
                rows.append({"ats": ats, "slug": slug, "status": "OK",
                             "jobs": total, "relevant": len(board_items)})
            except SlugNotFound:
                rows.append({"ats": ats, "slug": slug, "status": "404 (dead slug)",
                             "jobs": 0, "relevant": 0})
            except Exception as e:
                rows.append({"ats": ats, "slug": slug, "status": f"ERROR: {e}",
                             "jobs": 0, "relevant": 0})
    return rows
