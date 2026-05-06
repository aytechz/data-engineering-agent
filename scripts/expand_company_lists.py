#!/usr/bin/env python3
"""Expand the company token lists by pulling from public community-maintained lists.

Several open-source projects keep curated lists of Greenhouse / Lever / Ashby tokens.
We pull from a few of them and merge into our own data/companies_*.txt files.

Run this every couple of weeks to keep the lists fresh.

Usage:
    python scripts/expand_company_lists.py
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Iterable

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("expander")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Community-maintained sources. These are GitHub raw URLs that contain text/JSON
# with company tokens for the various ATS platforms. We extract tokens by regex.
#
# You can add more sources here — the script tolerates 404s.
SOURCES_GREENHOUSE = [
    # Pattern: extract anything that looks like a slug after `boards.greenhouse.io/`
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2025-Internships/dev/README.md",
    "https://raw.githubusercontent.com/speedyapply/2025-SWE-College-Jobs/main/README.md",
    "https://raw.githubusercontent.com/vanshb03/Summer2026-Internships/main/README.md",
]
SOURCES_LEVER = SOURCES_GREENHOUSE  # Same READMEs typically link both
SOURCES_ASHBY = SOURCES_GREENHOUSE

GH_PATTERNS = [
    re.compile(r"boards\.greenhouse\.io/([a-zA-Z0-9_\-]+)"),
    re.compile(r"job-boards\.greenhouse\.io/([a-zA-Z0-9_\-]+)"),
    re.compile(r"boards\.eu\.greenhouse\.io/([a-zA-Z0-9_\-]+)"),
]
LEVER_PATTERNS = [
    re.compile(r"jobs\.lever\.co/([a-zA-Z0-9_\-]+)"),
]
ASHBY_PATTERNS = [
    re.compile(r"jobs\.ashbyhq\.com/([a-zA-Z0-9_\-\.]+)"),
    re.compile(r"ashbyhq\.com/([a-zA-Z0-9_\-\.]+)"),
]


def _extract(text: str, patterns: list[re.Pattern]) -> set[str]:
    found: set[str] = set()
    for pat in patterns:
        for m in pat.findall(text):
            tok = m.lower().strip()
            # Filter junk and obvious non-tokens
            if 2 <= len(tok) <= 60 and tok not in {"jobs", "boards", "embed", "api", "v1", "applications"}:
                found.add(tok)
    return found


def _fetch(url: str, timeout: int = 30) -> str:
    try:
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent": "data-engineering-agent-expander/1.0"})
        if r.status_code != 200:
            log.warning("Source %s -> HTTP %d", url, r.status_code)
            return ""
        return r.text
    except requests.RequestException as e:
        log.warning("Source %s failed: %s", url, e)
        return ""


def _read_existing(path: Path) -> tuple[list[str], set[str]]:
    """Return (full_lines_including_comments, existing_token_set)."""
    if not path.exists():
        return [], set()
    lines = path.read_text().splitlines()
    tokens: set[str] = set()
    for raw in lines:
        line = raw.strip()
        if line and not line.startswith("#"):
            tokens.add(line.lower())
    return lines, tokens


def _append_new_tokens(path: Path, new_tokens: Iterable[str]) -> int:
    new_tokens = sorted({t.lower() for t in new_tokens})
    if not new_tokens:
        return 0
    lines, existing = _read_existing(path)
    truly_new = [t for t in new_tokens if t not in existing]
    if not truly_new:
        return 0
    section_header = "\n# ---- Auto-discovered (run scripts/expand_company_lists.py) ----"
    appended_block = section_header + "\n" + "\n".join(truly_new) + "\n"
    with path.open("a") as f:
        f.write(appended_block)
    return len(truly_new)


def expand(platform: str, sources: list[str], patterns: list[re.Pattern], target: Path) -> int:
    discovered: set[str] = set()
    for url in sources:
        text = _fetch(url)
        if text:
            discovered.update(_extract(text, patterns))
    log.info("[%s] discovered %d candidate tokens from %d sources",
             platform, len(discovered), len(sources))
    added = _append_new_tokens(target, discovered)
    log.info("[%s] appended %d new tokens to %s", platform, added, target.name)
    return added


def main() -> int:
    total = 0
    total += expand("greenhouse", SOURCES_GREENHOUSE, GH_PATTERNS,
                    DATA / "companies_greenhouse.txt")
    total += expand("lever", SOURCES_LEVER, LEVER_PATTERNS,
                    DATA / "companies_lever.txt")
    total += expand("ashby", SOURCES_ASHBY, ASHBY_PATTERNS,
                    DATA / "companies_ashby.txt")
    log.info("Done. Added %d tokens total. Run a scan to validate them.", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
