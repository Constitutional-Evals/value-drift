"""Parse the judge's line-format answers. Tolerant of bullets, code fences, extra spaces and stray commentary."""
from __future__ import annotations

import re

from .score import RELATIONS


def _lines(text: str):
    for raw in (text or "").splitlines():
        line = raw.strip().strip("`").strip()
        line = re.sub(r"^[-*•]\s+", "", line)
        if line:
            yield line


def parse_principles(text: str) -> list[dict]:
    out = []
    for line in _lines(text):
        parts = [p.strip() for p in line.split("|", 2)]
        if len(parts) >= 2 and re.fullmatch(r"P\d+", parts[0], re.I):
            kind, body = (parts[1], parts[2]) if len(parts) == 3 else ("", parts[1])
            if body:
                out.append({"id": parts[0].upper(), "text": body, "kind": kind.lower()})
    return out


def parse_matches(text: str) -> dict:
    """Lines 'P1 | relation | reason' and 'NEW | commitment'."""
    matches, new = [], []
    for line in _lines(text):
        if re.match(r"^NEW\b", line, re.I):
            parts = [p.strip() for p in line.split("|", 1)]
            if len(parts) == 2 and parts[1] and parts[1].lower().strip(". ") != "none":
                new.append(parts[1])
            continue
        parts = [p.strip() for p in line.split("|", 2)]
        if len(parts) >= 2 and re.fullmatch(r"P\d+", parts[0], re.I):
            rel = parts[1].lower().strip(". ")
            rel = {"absent": "dropped", "missing": "dropped", "kept": "same"}.get(rel, rel)
            matches.append({"a": parts[0].upper(), "b": None, "relation": rel, "note": parts[2] if len(parts) == 3 else ""})
    return {"matches": matches, "new": new}
