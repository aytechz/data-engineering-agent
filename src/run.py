#!/usr/bin/env python3
"""Main entry point — run a full scan cycle.

Steps:
  1. Load company lists from data/
  2. Fetch jobs from Greenhouse, Lever, Ashby concurrently
  3. Fetch from RemoteOK + HN Who is Hiring
  4. Apply filters
  5. Diff against data/seen_jobs.json to find truly new jobs
  6. Write data/seen_jobs.json, data/jobs.md, data/last_run.md
  7. Print Markdown summary to stdout (for GH Actions to file as an Issue)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import aiohttp
import yaml

# Make src/ importable when running from repo root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.companies import load_companies, write_dead_tokens_report
from src.filters import filter_job
from src.render import render_issue_title, render_jobs_feed, render_new_jobs_markdown
from src.scrapers_ats import run_all_ats
from src.scrapers_extra import fetch_hn_who_is_hiring, fetch_remoteok
from src.storage import load_seen, save_seen, split_new_vs_seen


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("agent")


def load_config(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f)


async def run_extras(skip: bool = False) -> list[dict[str, Any]]:
    if skip:
        return []
    headers = {"User-Agent": "data-engineering-agent/1.0"}
    async with aiohttp.ClientSession(headers=headers) as session:
        results = await asyncio.gather(
            fetch_remoteok(session),
            fetch_hn_who_is_hiring(session),
            return_exceptions=True,
        )
    out: list[dict[str, Any]] = []
    for r in results:
        if isinstance(r, Exception):
            log.warning("Extra source failed: %s", r)
            continue
        out.extend(r)
    return out


def find_dead_tokens(
    all_jobs: list[dict[str, Any]],
    companies: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Tokens that returned zero jobs this run — candidates for cleanup."""
    seen_tokens_by_source: dict[str, set[str]] = defaultdict(set)
    for j in all_jobs:
        seen_tokens_by_source[j["source"]].add((j.get("company") or "").lower())
    dead: dict[str, list[str]] = {}
    for source, tokens in companies.items():
        live = seen_tokens_by_source.get(source, set())
        dead[source] = [t for t in tokens if t not in live]
    return dead


async def main_async(args: argparse.Namespace) -> int:
    config = load_config(ROOT / "config.yaml")
    scan_cfg = config.get("scan", {}) or {}
    data_dir = ROOT / "data"

    companies = load_companies(data_dir)
    total_companies = sum(len(v) for v in companies.values())
    log.info("Loaded %d companies (greenhouse=%d, lever=%d, ashby=%d)",
             total_companies,
             len(companies["greenhouse"]), len(companies["lever"]), len(companies["ashby"]))

    if total_companies == 0:
        log.error("No companies configured! Check data/companies_*.txt files.")
        return 2

    # 1. Fetch from ATS platforms (the bulk of the work)
    ats_jobs = await run_all_ats(
        companies["greenhouse"],
        companies["lever"],
        companies["ashby"],
        concurrency=int(scan_cfg.get("concurrency", 50)),
        timeout=int(scan_cfg.get("request_timeout", 15)),
    )

    # 2. Fetch from extra sources
    extra_jobs = await run_extras(skip=args.skip_extras)

    all_jobs = ats_jobs + extra_jobs
    log.info("Total raw jobs fetched: %d", len(all_jobs))

    # 3. Apply filters
    matching: list[dict[str, Any]] = []
    for job in all_jobs:
        decision = filter_job(job, config)
        if decision.keep:
            job["_tags"] = decision.tags
            job["_matched_stack"] = decision.matched_stack
            matching.append(job)
    log.info("Jobs after filter: %d", len(matching))

    # 4. Diff against seen
    seen_path = data_dir / "seen_jobs.json"
    seen = load_seen(seen_path)
    new_jobs, updated_seen = split_new_vs_seen(matching, seen)
    log.info("Truly new jobs this run: %d", len(new_jobs))

    # 5. Persist seen-jobs map
    save_seen(seen_path, updated_seen,
              retention=int(scan_cfg.get("seen_jobs_retention", 50000)))

    # 6. Write reports
    last_run_md = render_new_jobs_markdown(new_jobs)
    (data_dir / "last_run.md").write_text(last_run_md)

    # The full feed: matching jobs from this run + we tag fingerprints; for simplicity
    # we use the current matching set as the feed source (jobs that are still live).
    # Attach _first_seen from the seen map for ordering.
    for j in matching:
        fp = j.get("_fingerprint")
        if fp and fp in updated_seen:
            j["_first_seen"] = updated_seen[fp]
    (data_dir / "jobs.md").write_text(render_jobs_feed(matching))

    # 7. Dead-token report (informational only)
    dead = find_dead_tokens(all_jobs, companies)
    write_dead_tokens_report(dead, data_dir / "dead_tokens.md")

    # 8. Stdout output for GH Actions (issue title + body)
    print("===NEW_JOBS_COUNT===")
    print(len(new_jobs))
    print("===ISSUE_TITLE===")
    print(render_issue_title(new_jobs))
    print("===ISSUE_BODY===")
    print(last_run_md)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan job boards for data engineering roles.")
    parser.add_argument("--skip-extras", action="store_true",
                        help="Skip RemoteOK / HN scrapers (useful for testing).")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
