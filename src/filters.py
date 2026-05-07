"""Filtering logic — decides which scraped jobs to keep and how to score/tag them."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re


@dataclass
class FilterDecision:
    """Result of running filters on a single job."""
    keep: bool
    reason: str = ""
    tags: list[str] = field(default_factory=list)
    matched_stack: list[str] = field(default_factory=list)

# Cache compiled patterns so we don't recompile per-job
_PATTERN_CACHE: dict[str, re.Pattern] = {}


def _compile(needle: str) -> re.Pattern:
    if needle not in _PATTERN_CACHE:
        # \b is word boundary — matches " data engineer " or "data engineer," but NOT "data engineering"
        _PATTERN_CACHE[needle] = re.compile(r"\b" + re.escape(needle) + r"\b", re.IGNORECASE)
    return _PATTERN_CACHE[needle]


def _text_contains_any(text: str, needles: list[str]) -> tuple[bool, str]:
    """Return (matched, first_match) for case-insensitive WHOLE-WORD search."""
    for needle in needles:
        if _compile(needle).search(text):
            return True, needle
    return False, ""

def filter_job(job: dict[str, Any], config: dict[str, Any]) -> FilterDecision:
    """Apply the configured filter rules to a single normalized job dict.

    Job is expected to have keys: title, description, location, company, source.
    Description may be empty if the source's list endpoint doesn't include it.
    """
    title = (job.get("title") or "").strip()
    description = (job.get("description") or "").strip()
    location = (job.get("location") or "").strip()
    haystack = f"{title}\n{description}"

    # Hard exclusions on title
    excluded, hit = _text_contains_any(title, config.get("exclude_title_keywords", []))
    if excluded:
        return FilterDecision(keep=False, reason=f"excluded_title:{hit}")

    # Must include at least one role keyword (in title)
    included, _ = _text_contains_any(title, config.get("include_title_keywords", []))
    if not included:
        return FilterDecision(keep=False, reason="no_role_keyword")

    # Seniority requirement
    if config.get("require_seniority", True):
        seniority_kw = config.get("seniority_keywords", [])
        has_seniority, _ = _text_contains_any(haystack, seniority_kw)
        if not has_seniority:
            return FilterDecision(keep=False, reason="no_seniority_signal")

    # Location filter
    allowed_locations = config.get("allowed_locations", [])
    if allowed_locations:
        if not location:
            if not config.get("keep_unknown_locations", True):
                return FilterDecision(keep=False, reason="unknown_location")
        else:
            location_ok, _ = _text_contains_any(location, allowed_locations)
            if not location_ok:
                return FilterDecision(keep=False, reason=f"location_not_allowed:{location}")

    # === We're keeping this job. Now compute tags + stack matches. ===
    tags: list[str] = []
    bonus_groups = config.get("bonus_tags", {}) or {}
    for tag_name, keywords in bonus_groups.items():
        matched, _ = _text_contains_any(haystack, keywords)
        if matched:
            tags.append(tag_name)

    matched_stack: list[str] = []
    for tech in config.get("preferred_stack", []):
        if _compile(tech).search(haystack):
            matched_stack.append(tech)

    return FilterDecision(keep=True, reason="match", tags=tags, matched_stack=matched_stack)
