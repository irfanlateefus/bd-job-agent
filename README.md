# BD Job Discovery Agent

An automated, AI-scored job-discovery pipeline for a **Business Development executive**.
It scrapes job listings on a schedule, scores each against your BD profile with a free
LLM (Gemini Flash), and writes a ranked, high-signal queue to **Notion** — so you review
a short list instead of hunting boards manually.

It learns: your Notion **Status** choices (Applied/Interested vs Skip/Rejected) feed back
into future scoring. Runs **100% free** on GitHub Actions.

```
COLLECT                          ENRICH                STORE
─────────────────────────────    ──────────────        ──────────
Company boards (GH/Lever/Ashby)  Gemini Flash          Notion DB
Aggregators (RemoteOK/Indeed/HN) 0–100 fit score   →   dedup by URL
Niche boards (RSS/HTML/PW)       2-sent summary        New/Interested/
LinkedIn (Playwright)            why it matches        Applied/Skip/Rejected
```

## Setup in under 5 minutes

1. **Clone & install**
   ```bash
   pip install -r requirements.txt
   python -m playwright install chromium   # required: LinkedIn is enabled by default (+ any method: playwright board)
   ```

2. **Get your keys**
   - **Notion token:** https://www.notion.so/my-integrations → New integration → copy the token.
   - **Notion parent page:** create/open a page, share it with your integration (••• → Connections),
     and copy its page id from the URL (the 32-char hex chunk).
   - **Gemini key (free):** https://aistudio.google.com/apikey

3. **Configure env**
   ```bash
   cp .env.example .env
   # fill in NOTION_TOKEN, NOTION_PARENT_PAGE_ID, GEMINI_API_KEY
   ```

4. **Create the database schema**
   ```bash
   python setup.py
   # prints NOTION_DATABASE_ID=... → paste it into .env
   ```

5. **(Recommended) Validate your company boards**
   ```bash
   python validate_sources.py   # shows which slugs are live vs 404
   ```

6. **Run it**
   ```bash
   python -m scraper.main
   ```

## Required secrets

| Name | Where used | How to get it |
|------|------------|---------------|
| `NOTION_TOKEN` | every run | notion.so/my-integrations |
| `NOTION_DATABASE_ID` | every run | printed by `python setup.py` |
| `NOTION_PARENT_PAGE_ID` | `setup.py` only | the Notion page id the integration can edit |
| `GEMINI_API_KEY` | enrichment | aistudio.google.com/apikey |

For the scheduled run, add `NOTION_TOKEN`, `NOTION_DATABASE_ID`, and `GEMINI_API_KEY`
under **GitHub → Settings → Secrets and variables → Actions**.

## Scheduling

`.github/workflows/scraper.yml` runs every 3 hours (cron `0 */3 * * *`) and on the
manual **Run workflow** button. Each run also syncs your latest Notion decisions and
commits `data/feedback.json`. Change the cron line to adjust the cadence.

## Customizing — everything lives in `config.yaml` and `profile/`

No keywords, companies, or filters are hardcoded in the Python.

### Add a company board
Drop the board **slug** under the right ATS in `config.yaml` — one line, no code:
```yaml
companies:
  greenhouse:
    - stripe
    - your-new-company      # ← add here
  lever:
    - netflix
  ashby:
    - ramp
```
Slug = the last path segment of the board URL:
- Greenhouse → `https://boards.greenhouse.io/<slug>`
- Lever → `https://jobs.lever.co/<slug>`
- Ashby → `https://jobs.ashbyhq.com/<slug>`

Then run `python validate_sources.py` to confirm the slug returns JSON.

### Edit the niche boards
```yaml
niche_boards:
  - name: WeWorkRemotely
    method: rss              # rss | html | playwright
    url: "https://weworkremotely.com/categories/remote-sales-and-marketing-jobs.rss"
```
Add any board with its `method`. Each board is isolated — one failing never breaks the others.

### Tune matching
- **Keywords** (the fast pre-filter): `filters.required_keywords` / `filters.blocked_keywords`.
- **Who you are** (how the AI scores fit): edit `profile/context.md`. Keep the highest-signal
  criteria near the top — the scorer reads the first 2000 characters.
- **Score floor:** `ai.min_score` (e.g. set to `60` to only store decent matches).
- **Aggregator queries / LinkedIn location:** under `aggregators` and `linkedin`.

## How it learns

`feedback_sync.py` reads your Notion **Status** column and distills it to
`data/feedback.json`:
- **Applied / Interested** → positive examples
- **Skip / Rejected** → negative examples

Those patterns are replayed into the scoring prompt on the next run, biasing scores toward
what you actually pursue. The workflow runs this automatically and commits the file.

## Project layout

```
bd-job-agent/
├── config.yaml              # all user-facing settings (sources, filters, AI, learning)
├── profile/context.md       # your BD matching profile (AI reads this)
├── scraper/
│   ├── main.py              # orchestrator: collect → dedupe → enrich → store
│   ├── filters.py           # config loader + fast keyword pre-filter
│   └── sources/             # one file per source group
│       ├── company_boards.py   # Greenhouse / Lever / Ashby
│       ├── aggregators.py      # RemoteOK / Indeed / HN Who's Hiring
│       ├── niche_boards.py     # rss / html / playwright dispatch
│       └── linkedin.py         # Playwright, isolated
├── ai/
│   ├── client.py            # Gemini REST + model fallback chain
│   ├── pipeline.py          # batched scoring
│   └── memory.py            # feedback replay
├── storage/notion_sync.py   # dedup-by-URL writes
├── data/feedback.json       # learned signal (committed by the workflow)
├── setup.py                 # create the Notion schema
├── validate_sources.py      # check which board slugs are live
├── enrich_existing.py       # backfill AI scores on old rows
├── feedback_sync.py         # pull Notion decisions into feedback.json
└── .github/workflows/scraper.yml
```

## Operational scripts

| Command | What it does |
|---------|--------------|
| `python setup.py` | Create the Notion database schema (run once) |
| `python -m scraper.main` | Full run: scrape → enrich → store |
| `python validate_sources.py` | Report which company-board slugs return JSON vs 404 |
| `python feedback_sync.py` | Refresh `data/feedback.json` from your Notion statuses |
| `python enrich_existing.py` | Backfill AI scores on rows that don't have one |

## Notes & limits

- **Free-tier safe:** Gemini calls are batched (5 listings/call) and rate-limited; the model
  auto-falls back across four models on quota errors.
- **Ethical scraping:** uses public APIs/feeds where possible; LinkedIn is conservative,
  isolated, and may return nothing if blocked — that's expected and never breaks a run.
- **Dedup:** by URL within a run and again against Notion before every write.
