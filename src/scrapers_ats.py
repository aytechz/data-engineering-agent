"""Scrapers for the three big ATS platforms — Greenhouse, Lever, Ashby.

All three expose public, unauthenticated JSON APIs for their job boards.
We hit them concurrently with aiohttp.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
LEVER_URL = "https://api.lever.co/v0/postings/{token}?mode=json"
ASHBY_URL = "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"


def _strip_html(html: str | None) -> str:
    if not html:
        return ""
    # Decode common HTML entities and strip tags. Good enough for keyword matching.
    text = re.sub(r"<[^>]+>", " ", html)
    text = (text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                .replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"'))
    return re.sub(r"\s+", " ", text).strip()


async def _get_json(session: aiohttp.ClientSession, url: str, timeout: int) -> dict | None:
    """GET a URL and return parsed JSON, or None on any error."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return None
            return await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return None


# ============================================================
# Greenhouse
# ============================================================
async def fetch_greenhouse(session: aiohttp.ClientSession, token: str, timeout: int) -> list[dict[str, Any]]:
    data = await _get_json(session, GREENHOUSE_URL.format(token=token), timeout)
    if not data or "jobs" not in data:
        return []

    out: list[dict[str, Any]] = []
    for j in data["jobs"]:
        out.append({
            "source": "greenhouse",
            "company": token,
            "company_display": (j.get("company_name") or token).strip(),
            "title": (j.get("title") or "").strip(),
            "location": ((j.get("location") or {}).get("name") or "").strip(),
            "description": _strip_html(j.get("content")),
            "url": j.get("absolute_url") or "",
            "external_id": str(j.get("id") or ""),
            "posted_at": j.get("updated_at") or "",
        })
    return out


# ============================================================
# Lever
# ============================================================
async def fetch_lever(session: aiohttp.ClientSession, token: str, timeout: int) -> list[dict[str, Any]]:
    data = await _get_json(session, LEVER_URL.format(token=token), timeout)
    # Lever returns a list directly (not wrapped in an object).
    if not isinstance(data, list):
        return []

    out: list[dict[str, Any]] = []
    for j in data:
        categories = j.get("categories") or {}
        location = categories.get("location") or ""
        # Lever has both descriptionPlain and description (HTML)
        desc = j.get("descriptionPlain") or _strip_html(j.get("description"))
        out.append({
            "source": "lever",
            "company": token,
            "company_display": token,
            "title": (j.get("text") or "").strip(),
            "location": location.strip() if isinstance(location, str) else "",
            "description": desc,
            "url": j.get("hostedUrl") or j.get("applyUrl") or "",
            "external_id": str(j.get("id") or ""),
            "posted_at": str(j.get("createdAt") or ""),
        })
    return out


# ============================================================
# Ashby
# ============================================================
async def fetch_ashby(session: aiohttp.ClientSession, token: str, timeout: int) -> list[dict[str, Any]]:
    data = await _get_json(session, ASHBY_URL.format(token=token), timeout)
    if not data or "jobs" not in data:
        return []

    out: list[dict[str, Any]] = []
    for j in data["jobs"]:
        out.append({
            "source": "ashby",
            "company": token,
            "company_display": token,
            "title": (j.get("title") or "").strip(),
            "location": (j.get("location") or "").strip(),
            "description": _strip_html(j.get("descriptionHtml") or j.get("descriptionPlain")),
            "url": j.get("jobUrl") or "",
            "external_id": str(j.get("id") or ""),
            "posted_at": j.get("publishedAt") or "",
        })
    return out


# ============================================================
# Concurrent runner across many companies
# ============================================================
async def run_all_ats(
    greenhouse_tokens: list[str],
    lever_tokens: list[str],
    ashby_tokens: list[str],
    concurrency: int = 50,
    timeout: int = 15,
) -> list[dict[str, Any]]:
    """Fetch all companies across all three platforms concurrently."""
    semaphore = asyncio.Semaphore(concurrency)
    headers = {"User-Agent": "data-engineering-agent/1.0 (+github.com/aytechz/data-engineering-agent)"}

    async with aiohttp.ClientSession(headers=headers) as session:
        async def bounded(coro):
            async with semaphore:
                return await coro

        tasks = []
        for t in greenhouse_tokens:
            tasks.append(bounded(fetch_greenhouse(session, t, timeout)))
        for t in lever_tokens:
            tasks.append(bounded(fetch_lever(session, t, timeout)))
        for t in ashby_tokens:
            tasks.append(bounded(fetch_ashby(session, t, timeout)))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_jobs: list[dict[str, Any]] = []
    error_count = 0
    for r in results:
        if isinstance(r, Exception):
            error_count += 1
            continue
        all_jobs.extend(r)

    log.info("Fetched %d total jobs across %d companies (%d errors)",
             len(all_jobs),
             len(greenhouse_tokens) + len(lever_tokens) + len(ashby_tokens),
             error_count)
    return all_jobs
