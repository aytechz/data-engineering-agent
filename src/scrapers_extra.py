"""Extra non-ATS sources: RemoteOK (clean JSON API) and HN 'Who is hiring?' thread."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

REMOTEOK_URL = "https://remoteok.com/api"
HN_LATEST_HIRING_SEARCH = (
    "https://hn.algolia.com/api/v1/search_by_date"
    "?query=Ask%20HN%20Who%20is%20hiring&tags=story&hitsPerPage=5"
)
HN_ITEM_URL = "https://hn.algolia.com/api/v1/items/{item_id}"


async def fetch_remoteok(session: aiohttp.ClientSession, timeout: int = 15) -> list[dict[str, Any]]:
    """RemoteOK ships a public JSON feed of all current postings."""
    headers = {"User-Agent": "data-engineering-agent/1.0"}
    try:
        async with session.get(REMOTEOK_URL, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
        log.warning("RemoteOK fetch failed: %s", e)
        return []

    if not isinstance(data, list):
        return []

    out: list[dict[str, Any]] = []
    for j in data:
        # First element of the RemoteOK feed is metadata, not a job.
        if not isinstance(j, dict) or "position" not in j:
            continue
        out.append({
            "source": "remoteok",
            "company": j.get("company") or "",
            "company_display": j.get("company") or "",
            "title": (j.get("position") or "").strip(),
            "location": (j.get("location") or "Remote").strip(),
            "description": (j.get("description") or "").strip(),
            "url": j.get("url") or j.get("apply_url") or "",
            "external_id": str(j.get("id") or j.get("slug") or ""),
            "posted_at": j.get("date") or "",
        })
    return out


async def fetch_hn_who_is_hiring(session: aiohttp.ClientSession, timeout: int = 30) -> list[dict[str, Any]]:
    """Pull the latest 'Ask HN: Who is hiring?' thread and parse top-level comments as job postings."""
    headers = {"User-Agent": "data-engineering-agent/1.0"}
    try:
        # 1. Find the most recent "Who is hiring?" submission by whoishiring user.
        async with session.get(HN_LATEST_HIRING_SEARCH, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return []
            search = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
        log.warning("HN search failed: %s", e)
        return []

    hits = search.get("hits", []) if isinstance(search, dict) else []
    target_id = None
    for h in hits:
        title = (h.get("title") or "").lower()
        author = (h.get("author") or "").lower()
        # The official monthly thread is by user "whoishiring"
        if author == "whoishiring" and "who is hiring" in title:
            target_id = h.get("objectID")
            break
    if not target_id:
        return []

    # 2. Fetch the full thread with all comments
    try:
        async with session.get(HN_ITEM_URL.format(item_id=target_id), headers=headers,
                               timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return []
            thread = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
        log.warning("HN thread fetch failed: %s", e)
        return []

    out: list[dict[str, Any]] = []
    for child in (thread.get("children") or []):
        text = child.get("text") or ""
        if not text:
            continue
        # Strip HTML
        plain = re.sub(r"<[^>]+>", " ", text)
        plain = re.sub(r"\s+", " ", plain).strip()
        # First line is conventionally: "Company | Role | Location | ..."
        first_line = plain.split(".", 1)[0][:300]
        out.append({
            "source": "hackernews",
            "company": _extract_company(first_line),
            "company_display": _extract_company(first_line),
            "title": first_line,
            "location": "",
            "description": plain[:5000],
            "url": f"https://news.ycombinator.com/item?id={child.get('id')}",
            "external_id": str(child.get("id") or ""),
            "posted_at": child.get("created_at") or datetime.now(timezone.utc).isoformat(),
        })
    return out


def _extract_company(first_line: str) -> str:
    """HN posts conventionally start with 'Company | ...'. Pull the first segment."""
    parts = re.split(r"\s*[|\-—:]\s*", first_line, maxsplit=1)
    return parts[0].strip()[:80] if parts else ""
