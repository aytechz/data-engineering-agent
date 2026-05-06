"""Render new jobs as Markdown for jobs.md, README, and GitHub Issues."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

TAG_EMOJI = {
    "healthcare": "🏥",
    "ai_ml": "🤖",
    "energy": "⚡",
}


def _job_line(job: dict[str, Any]) -> str:
    title = job.get("title") or "Untitled"
    company = job.get("company_display") or job.get("company") or "Unknown"
    location = job.get("location") or "Location not specified"
    url = job.get("url") or ""
    source = job.get("source") or "?"
    tags = job.get("_tags") or []
    stack = job.get("_matched_stack") or []

    tag_emojis = "".join(TAG_EMOJI.get(t, "") for t in tags)
    flag = f" {tag_emojis}" if tag_emojis else ""

    extras: list[str] = []
    if stack:
        extras.append(f"`{', '.join(stack[:6])}`")
    extras.append(f"_{source}_")
    extras_str = " · ".join(extras)

    if url:
        return f"- **[{title}]({url})** at **{company}** — {location}{flag} · {extras_str}"
    return f"- **{title}** at **{company}** — {location}{flag} · {extras_str}"


def render_new_jobs_markdown(new_jobs: list[dict[str, Any]]) -> str:
    """Markdown body grouped by source — for use in GitHub Issues and jobs.md."""
    if not new_jobs:
        return "_No new matching jobs this run._"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [f"### {len(new_jobs)} new matching jobs · {timestamp}", ""]

    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for j in new_jobs:
        by_source[j.get("source", "unknown")].append(j)

    for source in sorted(by_source.keys()):
        lines.append(f"#### From {source} ({len(by_source[source])})")
        for j in by_source[source]:
            lines.append(_job_line(j))
        lines.append("")

    return "\n".join(lines)


def render_jobs_feed(all_recent: list[dict[str, Any]], max_items: int = 200) -> str:
    """Full feed file written to jobs.md — most-recent jobs first."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = (
        "# Data Engineering Jobs Feed\n\n"
        f"_Last updated: {timestamp}_\n\n"
        f"Showing the {min(len(all_recent), max_items)} most recently discovered matching jobs.\n\n"
        "Tags: 🏥 healthcare · 🤖 AI/ML · ⚡ energy\n\n"
        "---\n"
    )
    sorted_jobs = sorted(
        all_recent,
        key=lambda j: j.get("_first_seen") or "",
        reverse=True,
    )[:max_items]
    body = "\n".join(_job_line(j) for j in sorted_jobs) or "_No jobs yet._"
    return header + "\n" + body + "\n"


def render_issue_title(new_jobs: list[dict[str, Any]]) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"[Jobs] {len(new_jobs)} new matches · {timestamp}"
