# data-engineering-agent

An automated job scanner that watches **thousands of company career pages every hour** and notifies you the moment a new Senior / Staff Data Engineering or Data Infrastructure role opens up.

Runs entirely on **GitHub Actions free tier**. No servers, no API keys, no recurring cost.

---

## How it works

1. **Hourly scheduled run** via GitHub Actions (`*/15 1 * * *` cron — every hour at :15).
2. The scanner hits the **public job-board APIs** of three major ATS platforms:
   - **Greenhouse**: `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs`
   - **Lever**: `https://api.lever.co/v0/postings/{slug}?mode=json`
   - **Ashby**: `https://api.ashbyhq.com/posting-api/job-board/{slug}`
3. Plus two extra sources: **RemoteOK** (public JSON feed) and **Hacker News "Who is hiring?"** (latest monthly thread).
4. Each job is filtered by your rules in `config.yaml` (title keywords, exclusions, seniority, location).
5. A SHA-1 fingerprint of `(source, company, job_id)` is compared against `data/seen_jobs.json` to find truly **new** postings.
6. New jobs are:
   - Posted to a **GitHub Issue** in this repo (you get email notifications from GitHub for free)
   - Written to `data/last_run.md` (just this run's matches)
   - Written to `data/jobs.md` (rolling feed of all currently-matching jobs)
7. The updated `seen_jobs.json` is committed back to the repo so the next run knows what's already been seen.

---

## Coverage

- **Seed list**: ~150 companies pre-loaded across the three platforms.
- **Easy expansion to thousands**: run `python scripts/expand_company_lists.py` to auto-discover company tokens from public community-maintained lists. Tokens that 404 or return zero jobs get logged to `data/dead_tokens.md` for cleanup.

The combined Greenhouse + Lever + Ashby reach is ~10,000+ companies in total. You can comfortably scan 3–5K of them per run within the 15-minute Actions timeout.

---

## Setup

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin git@github.com:aytechz/data-engineering-agent.git
git push -u origin main
```

### 2. Make sure Actions can write back

In your repo on GitHub:
- **Settings → Actions → General → Workflow permissions**
- Select **"Read and write permissions"**
- Check **"Allow GitHub Actions to create and approve pull requests"** (optional)

This lets the workflow commit updates to `seen_jobs.json` and create Issues.

### 3. (Optional) Expand the company list

```bash
pip install -r requirements.txt
python scripts/expand_company_lists.py
git add data/companies_*.txt
git commit -m "Expand company lists"
git push
```

### 4. Trigger your first run

Go to **Actions → Job Scan → Run workflow**. The first run will likely produce a large issue with all currently-matching jobs (because nothing is in `seen_jobs.json` yet). After that, every subsequent issue will only contain *new* jobs since the previous run.

---

## Configuring what jobs you see

Edit `config.yaml`. Key knobs:

- `include_title_keywords` — at least one must appear in the title (defaults: data engineer, data infrastructure, data platform, analytics engineer, ML engineer, etc.)
- `exclude_title_keywords` — drops anything matching (defaults: junior, intern, graduate, manager, director)
- `seniority_keywords` + `require_seniority` — require senior/staff/principal signal
- `allowed_locations` — substring-matched against the job's location field; empty list = allow everywhere
- `bonus_tags` — adds emoji flags to matching jobs (🏥 healthcare, 🤖 AI/ML, ⚡ energy)
- `preferred_stack` — Databricks, PySpark, Snowflake, etc. — shown as inline tags

Tweak the file, push, and the next run uses the new rules.

---

## Adding companies manually

Each ATS has its own file in `data/`:

- `data/companies_greenhouse.txt` — one slug per line
- `data/companies_lever.txt`
- `data/companies_ashby.txt`

To find a company's slug: look at their careers page URL.
- `boards.greenhouse.io/stripe` → token is `stripe`
- `jobs.lever.co/netflix` → token is `netflix`
- `jobs.ashbyhq.com/linear` → token is `linear`

After every run, `data/dead_tokens.md` lists tokens that returned zero jobs — review periodically and remove ones that look genuinely defunct.

---

## Local development

```bash
pip install -r requirements.txt
python -m src.run --skip-extras
```

Use `--skip-extras` to skip RemoteOK / HN scrapers during testing (they're a bit slower).

---

## Cost & limits

- **GitHub Actions free tier**: 2,000 min/month for private repos, unlimited for public repos.
- Each scan takes ~2–4 min depending on company count. Hourly = ~120 min/day = ~3,600 min/month for a private repo (you'll go slightly over the free tier with hourly + private).
- **Recommendations**:
  - Make the repo **public** for unlimited Actions minutes (the seen-jobs file isn't sensitive).
  - Or move to **every 2 hours** for private (~1,800 min/month, comfortably free).

---

## Files

```
data-engineering-agent/
├── .github/workflows/scan.yml      # Hourly scheduled GitHub Action
├── config.yaml                     # Filter rules (edit this)
├── requirements.txt                # aiohttp, pyyaml, requests
├── data/
│   ├── companies_greenhouse.txt    # One slug per line
│   ├── companies_lever.txt
│   ├── companies_ashby.txt
│   ├── seen_jobs.json              # Auto-managed dedup state
│   ├── jobs.md                     # Auto-generated rolling feed
│   ├── last_run.md                 # Auto-generated last-run summary
│   └── dead_tokens.md              # Auto-generated cleanup hints
├── scripts/
│   └── expand_company_lists.py     # Bulk-add tokens from community lists
└── src/
    ├── run.py                      # Main entry point
    ├── scrapers_ats.py             # Greenhouse / Lever / Ashby fetchers
    ├── scrapers_extra.py           # RemoteOK / HN
    ├── filters.py                  # Filter logic
    ├── companies.py                # Company list loader
    ├── storage.py                  # seen_jobs.json read/write/dedup
    └── render.py                   # Markdown rendering
```

---

## License

MIT — do whatever.
