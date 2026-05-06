"""Loads the lists of company tokens for each ATS platform from data/ files."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def _load_token_file(path: Path) -> list[str]:
    """Load a one-token-per-line file. Comments (#) and blanks are ignored."""
    if not path.exists():
        log.warning("Company list missing: %s", path)
        return []
    tokens: list[str] = []
    seen: set[str] = set()
    with path.open() as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            tok = line.lower()
            if tok not in seen:
                seen.add(tok)
                tokens.append(tok)
    return tokens


def load_companies(data_dir: Path) -> dict[str, list[str]]:
    """Return dict with keys 'greenhouse', 'lever', 'ashby' mapping to token lists."""
    return {
        "greenhouse": _load_token_file(data_dir / "companies_greenhouse.txt"),
        "lever": _load_token_file(data_dir / "companies_lever.txt"),
        "ashby": _load_token_file(data_dir / "companies_ashby.txt"),
    }


def write_dead_tokens_report(dead: dict[str, list[str]], path: Path) -> None:
    """Write a report of tokens that returned no jobs / 404 — useful for manual cleanup."""
    lines = ["# Tokens that returned 0 jobs in the last run.", "# Review and remove from companies_*.txt if persistently dead.", ""]
    for platform, tokens in dead.items():
        lines.append(f"## {platform} ({len(tokens)})")
        lines.extend(tokens)
        lines.append("")
    path.write_text("\n".join(lines))
