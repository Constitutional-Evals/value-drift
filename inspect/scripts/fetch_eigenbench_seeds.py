#!/usr/bin/env python3
"""Fetch and convert EigenBench provisional anchor constitutions into editable seeds.

    python scripts/fetch_eigenbench_seeds.py

Source: https://github.com/Constitutional-Evals/constitutions
        Provisional Constitutions/Provisional Anchors/
Pinned to commit c3d994e so a given seed is reproducible even if upstream changes.

The upstream files are **not constitutions** — they are EigenBench judge rubrics, JSON
with `overview`, 12 `criteria`, and 5 `guidelines`. Each criterion/guideline has:

    comparative  the normative statement            -> KEPT, becomes a principle
    reasoning    scholarly citations for it         -> DROPPED
    scenarios    two eval test prompts              -> DROPPED (critical)

Dropping `scenarios` is not optional. Those are evaluation prompts; a subject that read
them would know it was being evaluated, which would contaminate every condition.

Two deliberate choices, both recorded as limitations in data/constitutions/README.md:

- **No closing paragraph is invented.** `c0_broad_consensus` ends with "These principles
  are deliberately not given a fixed global priority order." That sentence is ours, not
  upstream's, and writing it into e.g. the Marxism seed would put a substantive claim in
  that value system's mouth. So these seeds have no such clause, and the "model introduces
  a priority ordering" measure is not directly comparable across seed families.
- **The title is generic**, matching c0, rather than naming the value system. The overview
  paragraph already makes the orientation plain; a branded title would add a signal c0
  does not have.

The repository carries no license file (`NOASSERTION`). Output is written to
data/constitutions/ and gitignored — fetched per-checkout rather than redistributed.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

COMMIT = "c3d994e91ba792156269fa2f9749b5f4d8c25f77"
# The upstream directory names contain spaces; every path segment is percent-encoded.
_DIR = urllib.parse.quote("Provisional Constitutions/Provisional Anchors")
BASE = (
    f"https://raw.githubusercontent.com/Constitutional-Evals/constitutions/{COMMIT}/{_DIR}"
)
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "constitutions"

# upstream filename -> our seed name
SEEDS = {
    "Universal_Kindness_Constitution.json": "c0_eb_universal_kindness",
    "Conservatism_Constitution.json": "c0_eb_conservatism",
    "Marxism_Constitution.json": "c0_eb_marxism",
}

TITLE = "# Constitution for a General-Purpose AI Assistant"


def to_markdown(doc: dict) -> str:
    """overview + the 17 `comparative` statements, as numbered principles."""
    items = list(doc.get("criteria", [])) + list(doc.get("guidelines", []))
    statements = [i["comparative"].strip() for i in items if i.get("comparative")]
    if not statements:
        raise ValueError("no `comparative` statements found — upstream format changed")
    body = "\n\n".join(f"{n}. {s}" for n, s in enumerate(statements, 1))
    return f"{TITLE}\n\n{doc['overview'].strip()}\n\n{body}\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for upstream, seed in SEEDS.items():
        url = f"{BASE}/{urllib.parse.quote(upstream)}"
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                doc = json.loads(r.read().decode("utf-8"))
        except Exception as ex:
            print(f"FAILED {upstream}: {ex}", file=sys.stderr)
            return 1

        # Guard: the eval scenarios must never reach the subject.
        md = to_markdown(doc)
        for item in list(doc.get("criteria", [])) + list(doc.get("guidelines", [])):
            for scenario in item.get("scenarios", []) or []:
                assert scenario.strip() not in md, "eval scenario leaked into the seed"

        path = OUT_DIR / f"{seed}.md"
        path.write_text(md, encoding="utf-8")
        n_principles = md.count("\n\n") - 1
        print(
            f"  {seed:<28} {len(md.split()):>5} words  "
            f"sha256={hashlib.sha256(md.encode()).hexdigest()[:12]}  -> {path.name}"
        )
    print(f"\n{len(SEEDS)} seeds written to {OUT_DIR} (pinned to {COMMIT[:7]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
