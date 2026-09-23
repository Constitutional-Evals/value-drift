#!/usr/bin/env python3
"""Fail if the results index and the filesystem disagree.

    python3 scripts/check_docs.py

This exists because documentation drifted from reality more than once: an experiment ran
and was never written up, and a writeup cited log paths that were a directory level off
from where the data actually was. Both are the kind of thing a reminder to "be careful
next time" does not fix. This is a check instead.

It verifies three things:

1. Every directory under logs/ has an entry in results/runs.yaml (except the skip list).
2. Every path named in runs.yaml actually exists.
3. Every run entry carries the fields the index needs to be useful.

Exit code is 0 when clean, 1 when anything is wrong. Safe to wire into CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - dependency is declared in pyproject
    sys.exit("check_docs.py needs pyyaml: python3 -m pip install -e '.[dev]'")

REPO = Path(__file__).resolve().parent.parent
RUNS_YAML = REPO / "results" / "runs.yaml"

# Directories under logs/ that are not experiments.
#   _archive  earlier exploratory runs, kept for provenance
#   smoke     output of tests/smoke.py, regenerated freely
SKIP_LOG_DIRS = {"_archive", "smoke"}

# Fields every entry must carry. `inspect_version` is intentionally not required —
# it is a known TODO that isn't recorded at run time yet.
COMMON_FIELDS = ("id", "date", "models", "runs", "cost_usd", "writeup", "status")

# A run is one of two shapes, and carries the location fields for its shape:
#   chain     recursive lineages under chains/<id>/, self-contained
#   singleshot  one eval under logs/<id>/, flattened into exports/<id>/
SHAPE_FIELDS = {
    "chain": ("chain_dir",),
    "singleshot": ("log_dir", "export_dir"),
}

# Fields whose value is a repo-relative path that must exist on disk.
PATH_FIELDS = ("log_dir", "export_dir", "chain_dir", "writeup")


def shape_of(entry: dict) -> str:
    return "chain" if entry.get("chain_dir") else "singleshot"


def main() -> int:
    problems: list[str] = []

    if not RUNS_YAML.exists():
        print(f"FAIL  {RUNS_YAML.relative_to(REPO)} does not exist")
        return 1

    data = yaml.safe_load(RUNS_YAML.read_text(encoding="utf-8")) or {}
    entries = data.get("runs") or []
    if not entries:
        problems.append("runs.yaml has no `runs:` entries")

    # --- 1. every entry is complete, and its paths exist ---------------------------
    declared_dirs: set[str] = set()
    for i, entry in enumerate(entries):
        label = entry.get("id") or f"entry #{i + 1}"

        for field in COMMON_FIELDS + SHAPE_FIELDS[shape_of(entry)]:
            if not entry.get(field):
                problems.append(f"{label}: missing required field `{field}`")

        for field in PATH_FIELDS:
            value = entry.get(field)
            if value and not (REPO / value).exists():
                problems.append(f"{label}: `{field}` points at {value}, which does not exist")

        for field in ("log_dir", "chain_dir"):
            if entry.get(field):
                declared_dirs.add(entry[field])

    # --- 2. every run directory is accounted for -----------------------------------
    for root in ("logs", "chains"):
        root_path = REPO / root
        if not root_path.is_dir():
            continue
        for child in sorted(root_path.iterdir()):
            if not child.is_dir() or child.name in SKIP_LOG_DIRS:
                continue
            rel = f"{root}/{child.name}"
            if rel not in declared_dirs:
                problems.append(
                    f"{rel} has no entry in results/runs.yaml "
                    f"(add one, or move it to {root}/_archive/ if it is not a result)"
                )

    # --- report --------------------------------------------------------------------
    if problems:
        print(f"FAIL  {len(problems)} problem(s):\n")
        for p in problems:
            print(f"  - {p}")
        print("\nSee docs/running-your-own.md for what an entry should look like.")
        return 1

    n = len(entries)
    total_runs = sum(e.get("runs", 0) for e in entries)
    total_cost = sum(e.get("cost_usd", 0) for e in entries)
    print(f"OK  {n} experiment(s), {total_runs} runs, ${total_cost:.2f} — index matches disk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
