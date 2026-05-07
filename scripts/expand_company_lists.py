#!/usr/bin/env python3
"""Expand the company token lists from high-quality public sources.

Primary source: github.com/Feashliaa/job-board-aggregator (CC BY-NC 4.0)
"""
from __future__ import annotations
import json, logging, re, sys
from pathlib import Path
from typing import Iterable
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("expander")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

FEASHLIAA_BASE = "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data"
SOURCES = {
    "greenhouse": [f"{FEASHLIAA_BASE}/greenhouse_companies.json",
                   f"{FEASHLIAA_BASE}/companies_greenhouse.json"],
    "lever":      [f"{FEASHLIAA_BASE}/lever_companies.json",
                   f"{FEASHLIAA_BASE}/companies_lever.json"],
    "ashby":      [f"{FEASHLIAA_BASE}/ashby_companies.json",
                   f"{FEASHLIAA_BASE}/companies_ashby.json"],
}

JUNK = {"jobs","boards","embed","api","v1","applications","search","company",
        "careers","career","p","form","image","images","src","main","master",
        "static","assets","data","www"}

def _fetch(url, timeout=30):
    try:
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent":"de-agent-expander/2.0"})
        return r.text if r.status_code == 200 else ""
    except requests.RequestException:
        return ""

def _valid(t):
    return bool(t) and 2 <= len(t) <= 60 and t not in JUNK and re.match(r"^[a-zA-Z0-9]", t)

def _from_json(text):
    try: data = json.loads(text)
    except json.JSONDecodeError: return set()
    out = set()
    def add(v):
        if isinstance(v, str):
            t = v.strip().lower()
            if _valid(t): out.add(t)
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str): add(item)
            elif isinstance(item, dict):
                for k in ("slug","token","board_token","url_token","id","name"):
                    if k in item: add(item[k]); break
    elif isinstance(data, dict):
        for k in data: add(k)
    return out

def _read_existing(path):
    if not path.exists(): return set()
    return {l.strip().lower() for l in path.read_text().splitlines()
            if l.strip() and not l.strip().startswith("#")}

def _append(path, tokens):
    tokens = sorted({t.lower() for t in tokens})
    if not tokens: return 0
    existing = _read_existing(path)
    new = [t for t in tokens if t not in existing]
    if not new: return 0
    with path.open("a") as f:
        f.write("\n# ---- Auto-discovered ----\n" + "\n".join(new) + "\n")
    return len(new)

def expand(platform, target):
    discovered = set()
    for url in SOURCES[platform]:
        text = _fetch(url)
        if text:
            tokens = _from_json(text)
            if tokens:
                log.info("[%s] %s -> %d tokens", platform, url.split('/')[-1], len(tokens))
                discovered.update(tokens)
    log.info("[%s] %d total candidates", platform, len(discovered))
    added = _append(target, discovered)
    log.info("[%s] appended %d NEW tokens", platform, added)
    return added

def main():
    total = sum(expand(p, DATA / f"companies_{p}.txt") for p in ("greenhouse","lever","ashby"))
    log.info("=" * 50)
    log.info("Done. Added %d new tokens.", total)
    return 0

if __name__ == "__main__":
    sys.exit(main())