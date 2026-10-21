"""Scenario sets: the 44 value probes plus a wider set (evals/scenarios.jsonl).

A row is {"id", "category", "prompt"} with optional "axis" (value probes only), "system"
(an operator/system prompt) and "history" (earlier turns of a multi-turn conversation).
`to_messages` turns a row into the chat messages to render.
"""
from __future__ import annotations

from pathlib import Path

from oct.common import read_jsonl

HERE = Path(__file__).parent
DEFAULT_SETS = [HERE / "probes.jsonl", HERE / "scenarios.jsonl"]


def load_scenarios(paths: list[Path] | None = None, limit_per_category: int | None = None) -> list[dict]:
    rows, seen = [], set()
    for p in paths or DEFAULT_SETS:
        for r in read_jsonl(p):
            if r["id"] in seen:
                raise ValueError(f"duplicate scenario id {r['id']!r} in {p}")
            seen.add(r["id"])
            r.setdefault("category", "value_probe")
            rows.append(r)
    if limit_per_category:
        kept, count = [], {}
        for r in rows:
            count[r["category"]] = count.get(r["category"], 0) + 1
            if count[r["category"]] <= limit_per_category:
                kept.append(r)
        rows = kept
    return rows


def to_messages(row: dict) -> list[dict]:
    msgs = [{"role": "system", "content": row["system"]}] if row.get("system") else []
    return msgs + list(row.get("history", [])) + [{"role": "user", "content": row["prompt"]}]


def transcript(row: dict) -> str:
    """The conversation as a judge should see it. Plain prompts are returned unchanged."""
    if not row.get("system") and not row.get("history"):
        return row["prompt"]
    return "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in to_messages(row))
