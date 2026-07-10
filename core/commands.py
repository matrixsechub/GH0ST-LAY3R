"""
Ghost Layer Studio — Tri-Vector Command Parser

# ADVANCEMENT: Ecosystem contracts
Parses MSH tri-vector command syntax: CATEGORY::TARGET::PARAMETER
"""

from __future__ import annotations
from typing import Optional

ALLOWED_CATEGORIES = frozenset(
    {
        "ANALYZE",
        "SCAN",
        "GENERATE",
        "SYNTH",
        "DEPLOY",
        "LOOP",
        "PLAN",
        "AGGREGATE",
    }
)


def parse_command(command: str) -> dict:
    """
    Parse a tri-vector command string.

    Returns a dict with keys: raw, category, target, parameter, ok, error.
    """
    raw = command if isinstance(command, str) else str(command)
    stripped = raw.strip()

    if not stripped:
        return _invalid(raw, "command must not be empty")

    segments = stripped.split("::")
    if len(segments) != 3:
        return _invalid(
            raw,
            "command must have exactly three segments (CATEGORY::TARGET::PARAMETER)",
        )

    category_raw, target_raw, parameter_raw = segments
    category = category_raw.strip().upper()
    target = target_raw.strip()
    parameter = parameter_raw.strip()

    if not category:
        return _invalid(raw, "category segment must not be empty")
    if not target:
        return _invalid(raw, "target segment must not be empty")
    if not parameter:
        return _invalid(raw, "parameter segment must not be empty")

    if category not in ALLOWED_CATEGORIES:
        return _invalid(
            raw,
            f"unknown category '{category_raw.strip()}'; "
            f"allowed: {', '.join(sorted(ALLOWED_CATEGORIES))}",
        )

    return {
        "raw": raw,
        "category": category,
        "target": target,
        "parameter": parameter,
        "ok": True,
        "error": None,
    }


def validate_command(command: str) -> dict:
    """Validate and parse *command*; returns the same shape as parse_command."""
    return parse_command(command)


def _invalid(raw: str, reason: str) -> dict:
    return {
        "raw": raw,
        "category": None,
        "target": None,
        "parameter": None,
        "ok": False,
        "error": reason,
    }
