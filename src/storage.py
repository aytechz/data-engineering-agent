"""Tracks which jobs have been seen across runs (dedup via JSON file in repo)."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def job_fingerprint(job: dict[str, Any]) -> str:
    """Stable hash for dedup. Combines source + company + external_id (or title fallback)."""
    key_parts = [
        (job.get("source") or "").lower(),
        (job.get("company") or "").lower(),
        (job.get("external_id") or job.get("title") or "").lower(),
    ]
    raw = "|".join(key_parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def load_seen(path: Path) -> dict[str, str]:
    """Returns {fingerprint: first_seen_iso}."""
    if not path.exists():
        return {}
    try:
        with path.open() as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Could not load %s: %s — starting fresh", path, e)
    return {}


def save_seen(path: Path, seen: dict[str, str], retention: int = 50000) -> None:
    """Persist seen-jobs map. Trim oldest entries if exceeding retention."""
    if len(seen) > retention:
        # Keep the newest `retention` entries by timestamp value
        sorted_items = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:retention]
        seen = dict(sorted_items)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(seen, f, indent=0, sort_keys=True)


def split_new_vs_seen(
    jobs: list[dict[str, Any]],
    seen: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Return (new_jobs, updated_seen_map)."""
    now = datetime.now(timezone.utc).isoformat()
    new_jobs: list[dict[str, Any]] = []
    updated = dict(seen)
    for job in jobs:
        fp = job_fingerprint(job)
        if fp not in updated:
            updated[fp] = now
            job["_fingerprint"] = fp
            job["_first_seen"] = now
            new_jobs.append(job)
    return new_jobs, updated
