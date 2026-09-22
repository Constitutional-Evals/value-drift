#!/usr/bin/env python3
"""Export completed Inspect logs to one flat record per sample/epoch.

Descriptive only: no embeddings, no value axes, no hypothesis tests (build spec §9).

    python scripts/export_runs.py --log-dir logs --out exports/run1

Produces, under the output directory:

    runs.csv                    one row per independent run
    runs.jsonl                  the same rows, plus the full diff
    constitutions/<run>.md      each final artifact, as a plain file
    diffs/<run>.diff            each unified diff against C0

`<run>` is `<log-id>__<sample-id>__epoch<N>`, so runs stay distinguishable across logs.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

from inspect_ai.log import EvalLog, list_eval_logs, read_eval_log

from constitutional_drift.content import CATEGORIES

SCORER = "constitution_change"

# Column order for runs.csv. `diff` and `final_constitution` are deliberately excluded:
# they are multi-line artifacts and live in their own files (and in runs.jsonl).
COLUMNS = [
    "run",
    "log",
    "model",
    "reasoning_effort",
    "reasoning_tokens",
    "temperature",
    "sample_id",
    "epoch",
    "seed",
    "task",
    "embodiment",
    "tools",
    "authority",
    "identity",
    "mechanism",
    "permissions",
    "deliberation",
    "changed",
    "changed_raw",
    "introduced",
    *[f"added_{c}" for c in CATEGORIES],
    "seed_baseline",
    "principles_before",
    "principles_after",
    "principles_added",
    "principles_removed",
    "principles_modified",
    "change_ratio",
    "lines_added",
    "lines_deleted",
    "lines_modified",
    "permission_violation",
    "unsanctioned_edit",
    "constitution_deleted",
    "c0_lines_preserved",
    "net_line_growth",
    "extra_files",
    "c0_sha256",
    "final_sha256",
    "initial_chars",
    "initial_words",
    "initial_lines",
    "final_chars",
    "final_words",
    "final_lines",
    "n_messages",
    "n_editor_calls",
    "n_bash_calls",
    "n_think_calls",
    "stop_reason",
    "limit_hit",
    "total_time",
    "working_time",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "error",
]


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")


def _usage(sample: Any) -> dict[str, int]:
    """Sum token usage across every model the sample touched."""
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for usage in (sample.model_usage or {}).values():
        totals["input_tokens"] += usage.input_tokens or 0
        totals["output_tokens"] += usage.output_tokens or 0
        totals["total_tokens"] += usage.total_tokens or 0
    return totals


def _tool_calls(sample: Any) -> dict[str, int]:
    """Count subject tool calls straight from the transcript."""
    counts = {"n_editor_calls": 0, "n_bash_calls": 0, "n_think_calls": 0}
    key = {"text_editor": "n_editor_calls", "bash": "n_bash_calls", "think": "n_think_calls"}
    for message in sample.messages or []:
        for call in getattr(message, "tool_calls", None) or []:
            if call.function in key:
                counts[key[call.function]] += 1
    return counts


def records_for_log(log: EvalLog) -> list[dict[str, Any]]:
    """One record per sample/epoch in a single eval log."""
    config = log.eval.model_generate_config
    log_id = _slug(Path(log.location).stem)[:40]
    rows: list[dict[str, Any]] = []

    for sample in log.samples or []:
        score = (sample.scores or {}).get(SCORER)
        meta: dict[str, Any] = dict(score.metadata or {}) if score else {}
        condition: dict[str, str] = meta.get("condition") or (
            (sample.metadata or {}).get("condition") or {}
        )
        run = f"{log_id}__{_slug(str(sample.id))}__epoch{sample.epoch}"

        rows.append(
            {
                "run": run,
                "log": Path(log.location).name,
                "model": log.eval.model,
                # Reasoning configuration as the provider was actually asked for it.
                # Absent here means the run used the provider default, not "off".
                "reasoning_effort": config.reasoning_effort,
                "reasoning_tokens": config.reasoning_tokens,
                "temperature": config.temperature,
                "sample_id": sample.id,
                "epoch": sample.epoch,
                **{k: condition.get(k) for k in
                   ("seed", "task", "embodiment", "tools", "authority",
                    "identity", "mechanism", "permissions", "deliberation")},
                "changed": meta.get("changed"),
                "changed_raw": meta.get("changed_raw"),
                "introduced": ";".join(meta.get("introduced") or []),
                **{f"added_{c}": meta.get(f"added_{c}") for c in CATEGORIES},
                "seed_baseline": ";".join(meta.get("seed_baseline") or []),
                **{k: meta.get(k) for k in
                   ("principles_before", "principles_after", "principles_added",
                    "principles_removed", "principles_modified")},
                "new_principles": meta.get("new_principles"),
                "change_ratio": meta.get("change_ratio"),
                "lines_added": meta.get("lines_added"),
                "lines_deleted": meta.get("lines_deleted"),
                "lines_modified": meta.get("lines_modified"),
                "permission_violation": meta.get("permission_violation"),
                "unsanctioned_edit": meta.get("unsanctioned_edit"),
                "constitution_deleted": meta.get("constitution_deleted"),
                "c0_lines_preserved": meta.get("c0_lines_preserved"),
                "net_line_growth": meta.get("net_line_growth"),
                "extra_files": ";".join(meta.get("extra_files") or []),
                "c0_sha256": meta.get("c0_sha256"),
                "final_sha256": meta.get("final_sha256"),
                **{k: meta.get(k) for k in
                   ("initial_chars", "initial_words", "initial_lines",
                    "final_chars", "final_words", "final_lines")},
                "n_messages": len(sample.messages or []),
                **_tool_calls(sample),
                "stop_reason": getattr(sample.output, "stop_reason", None),
                "limit_hit": sample.limit.type if sample.limit else None,
                "total_time": sample.total_time,
                "working_time": sample.working_time,
                **_usage(sample),
                "error": str(sample.error) if sample.error else None,
                # jsonl-only, dropped from the csv
                "diff": meta.get("diff"),
                "final_constitution": meta.get("final_constitution"),
                "submission": score.answer if score else None,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", default="logs", help="directory of .eval logs")
    parser.add_argument("--out", default="exports/latest", help="output directory")
    args = parser.parse_args()

    log_infos = list_eval_logs(args.log_dir)
    if not log_infos:
        print(f"no eval logs found under {args.log_dir}")
        return 1

    out = Path(args.out)
    (out / "constitutions").mkdir(parents=True, exist_ok=True)
    (out / "diffs").mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for info in log_infos:
        log = read_eval_log(info.name)
        if log.status != "success":
            print(f"skipping {Path(info.name).name}: status={log.status}")
            continue
        rows.extend(records_for_log(log))

    for row in rows:
        if row["final_constitution"]:
            (out / "constitutions" / f"{row['run']}.md").write_text(
                row["final_constitution"], encoding="utf-8"
            )
        if row["diff"]:
            (out / "diffs" / f"{row['run']}.diff").write_text(row["diff"], encoding="utf-8")

    with (out / "runs.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    with (out / "runs.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    changed = sum(1 for r in rows if r["changed"])
    print(f"{len(rows)} runs from {len(log_infos)} log(s) -> {out}")
    print(f"  edit rate: {changed}/{len(rows)}" + (f" = {changed / len(rows):.3f}" if rows else ""))
    print(f"  runs.csv, runs.jsonl, constitutions/*.md, diffs/*.diff")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
