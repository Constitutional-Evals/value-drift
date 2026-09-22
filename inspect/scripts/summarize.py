#!/usr/bin/env python3
"""Per-cell summary table straight from Inspect logs.

    python scripts/summarize.py --log-dir logs/s1-authority
    python scripts/summarize.py --log-dir logs/s3-framing --by identity,mechanism

With no --by, it groups by whichever factors actually vary in the logs, which is the
right thing for a one-factor sweep and for a 2x2.

Descriptive only. `edit%` is the headline, but read `ratio` and the line counts too:
if every run edits, edit% saturates at 100% and all the signal moves to magnitude.
"""

from __future__ import annotations

import argparse
import statistics
from collections import defaultdict
from typing import Any

from inspect_ai.log import list_eval_logs, read_eval_log

from constitutional_drift.content import CATEGORIES

FACTORS = ["seed", "task", "embodiment", "tools", "authority", "identity",
           "mechanism", "permissions", "deliberation"]

# $ per 1M tokens (input, output). Used only for a spend readout, never for scoring.
# Anthropic bills cache writes at 1.25x the input rate and cache reads at 0.1x.
CACHE_WRITE_MULT = 1.25
CACHE_READ_MULT = 0.10

PRICES = {
    "claude-sonnet-5": (2.0, 10.0),
    "gpt-5": (1.25, 10.0),
    "grok-4.6": (2.0, 6.0),
    "grok-4.3": (1.25, 2.5),
    "deepseek-chat-v3.1": (0.25, 0.95),
    "gemini-2.5-pro": (1.25, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5-1": (10.0, 50.0),
}


def price_for(model: str) -> tuple[float, float] | None:
    name = model.split("/")[-1]
    return PRICES.get(name)


def collect(log_dir: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for info in list_eval_logs(log_dir):
        log = read_eval_log(info.name)
        if log.status != "success":
            print(f"  (skipping {info.name}: status={log.status})")
            continue
        for sample in log.samples or []:
            score = (sample.scores or {}).get("constitution_change")
            if not score:
                continue
            meta = dict(score.metadata or {})
            row = dict(meta.get("condition") or {})
            row.update(
                model=log.eval.model,
                effort=log.eval.model_generate_config.reasoning_effort,
                changed=bool(meta.get("changed")),
                ratio=meta.get("change_ratio") or 0.0,
                added=meta.get("lines_added") or 0,
                deleted=meta.get("lines_deleted") or 0,
                modified=meta.get("lines_modified") or 0,
                violation=meta.get("permission_violation"),
                final_words=meta.get("final_words") or 0,
                initial_words=meta.get("initial_words") or 0,
                editor_calls=sum(
                    1
                    for m in (sample.messages or [])
                    for c in (getattr(m, "tool_calls", None) or [])
                    if c.function == "text_editor"
                ),
                limit=sample.limit.type if sample.limit else None,
                error=bool(sample.error),
                introduced=set(meta.get("introduced") or []),
                seed_baseline=meta.get("seed_baseline") or [],
                principles_added=meta.get("principles_added") or 0,
                principles_removed=meta.get("principles_removed") or 0,
                principles_modified=meta.get("principles_modified") or 0,
                input_tokens=sum(
                    u.input_tokens or 0 for u in (sample.model_usage or {}).values()
                ),
                output_tokens=sum(
                    u.output_tokens or 0 for u in (sample.model_usage or {}).values()
                ),
                cache_write=sum(
                    u.input_tokens_cache_write or 0
                    for u in (sample.model_usage or {}).values()
                ),
                cache_read=sum(
                    u.input_tokens_cache_read or 0
                    for u in (sample.model_usage or {}).values()
                ),
                reasoning_tokens=sum(
                    u.reasoning_tokens or 0 for u in (sample.model_usage or {}).values()
                ),
                model_calls=sum(
                    1 for m in (sample.messages or []) if m.role == "assistant"
                ),
            )
            rows.append(row)
    return rows


def varying_factors(rows: list[dict[str, Any]]) -> list[str]:
    varying = [f for f in FACTORS if len({r.get(f) for r in rows}) > 1]
    return varying or ["authority"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log-dir", default="logs")
    ap.add_argument("--by", help="comma-separated factors to group by")
    args = ap.parse_args()

    rows = collect(args.log_dir)
    if not rows:
        print(f"no scored samples under {args.log_dir}")
        return 1

    by = [f.strip() for f in args.by.split(",")] if args.by else varying_factors(rows)

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(f) for f in by)] = groups[tuple(row.get(f) for f in by)]
        groups[tuple(row.get(f) for f in by)].append(row)

    models = sorted({r["model"] for r in rows})
    efforts = sorted({str(r["effort"]) for r in rows})
    print(f"\n{len(rows)} runs · model(s): {', '.join(models)} · reasoning_effort: {', '.join(efforts)}")
    print(f"grouped by: {', '.join(by)}\n")

    label_w = max(28, max(len(" / ".join(str(v) for v in k)) for k in groups))
    header = (
        f"{'cell'.ljust(label_w)}  {'n':>3}  {'edit%':>6}  {'ratio':>6}  "
        f"{'+ln':>5}  {'-ln':>5}  {'~ln':>5}  {'words':>6}  {'edits':>5}  {'viol':>5}"
    )
    print(header)
    print("-" * len(header))

    for key in sorted(groups):
        g = groups[key]
        n = len(g)
        edited = [r for r in g if r["changed"]]
        rate = len(edited) / n
        # Magnitude is conditional on having edited — averaging in the zeros of
        # unchanged runs conflates "rarely edits" with "edits a little".
        ratio = statistics.mean(r["ratio"] for r in edited) if edited else 0.0
        mean = lambda k: statistics.mean(r[k] for r in edited) if edited else 0.0
        dw = (
            statistics.mean(r["final_words"] - r["initial_words"] for r in edited)
            if edited
            else 0.0
        )
        viols = [r for r in g if r["violation"] is True]
        viol = f"{len(viols)}/{n}" if any(r["violation"] is not None for r in g) else "-"
        print(
            f"{' / '.join(str(v) for v in key).ljust(label_w)}  {n:>3}  "
            f"{rate * 100:>5.0f}%  {ratio:>6.3f}  {mean('added'):>5.1f}  "
            f"{mean('deleted'):>5.1f}  {mean('modified'):>5.1f}  {dw:>+6.0f}  "
            f"{mean('editor_calls'):>5.1f}  {viol:>5}"
        )

    # Spend readout. Prompt caching is on, so uncached `input_tokens` is near zero and
    # the real input spend sits in cache writes (1.25x) and reads (0.1x).
    n = len(rows)
    tin = sum(r["input_tokens"] for r in rows)
    tcw = sum(r["cache_write"] for r in rows)
    tcr = sum(r["cache_read"] for r in rows)
    tout = sum(r["output_tokens"] for r in rows)
    treason = sum(r["reasoning_tokens"] for r in rows)
    calls = statistics.mean(r["model_calls"] for r in rows)
    print(f"\n{n} runs · {calls:.1f} model calls per run")
    print(
        f"tokens/run: {tin / n:,.0f} input · {tcw / n:,.0f} cache-write · "
        f"{tcr / n:,.0f} cache-read · {tout / n:,.0f} output "
        f"(of which {treason / n:,.0f} reasoning"
        + (f", {treason / tout * 100:.0f}%)" if tout else ")")
    )
    price = price_for(models[0]) if len(models) == 1 else None
    if price and (tin or tcw or tout):
        pin, pout = price
        cost = (
            tin / 1e6 * pin
            + tcw / 1e6 * pin * CACHE_WRITE_MULT
            + tcr / 1e6 * pin * CACHE_READ_MULT
            + tout / 1e6 * pout
        )
        out_share = tout / 1e6 * pout / cost * 100 if cost else 0
        print(
            f"cost:       ${cost:.2f} total = ${cost / n:.4f} per run "
            f"(at ${pin:g}/${pout:g} per 1M; {out_share:.0f}% of it output)"
        )
        print(f"            -> 72-run sweep ≈ ${cost / n * 72:.2f}")

    # --- content table: the measure change_ratio could not see ---------------------
    print(f"\n{'cell'.ljust(label_w)}  {'n':>3}" + "".join(
        f"{c[:11]:>13}" for c in CATEGORIES) + f"{'+prin':>7}{'-prin':>7}{'~prin':>7}")
    print("-" * (label_w + 5 + 13 * len(CATEGORIES) + 21))
    for key in sorted(groups):
        g = groups[key]
        n = len(g)
        line = f"{' / '.join(str(v) for v in key).ljust(label_w)}  {n:>3}"
        for c in CATEGORIES:
            hits = sum(1 for r in g if c in r["introduced"])
            line += f"{f'{hits}/{n}':>13}"
        ed = [r for r in g if r["changed"]] or g
        line += (
            f"{statistics.mean(r['principles_added'] for r in ed):>7.1f}"
            f"{statistics.mean(r['principles_removed'] for r in ed):>7.1f}"
            f"{statistics.mean(r['principles_modified'] for r in ed):>7.1f}"
        )
        print(line)
    baselines = sorted({b for r in rows for b in (r.get("seed_baseline") or [])})
    if baselines:
        print(f"\nseed already carried: {', '.join(baselines)} "
              "— read those columns with care")
    print("\ncategory columns = runs that INTRODUCED that topic (not already in the seed)")

    stuck = [r for r in rows if r["limit"] or r["error"]]
    if stuck:
        print(f"\n{len(stuck)} run(s) hit a limit or errored — check before interpreting.")
    print(
        "\nedit% = ran changed the document at all · ratio, +ln/-ln/~ln, words, edits\n"
        "are means over EDITED runs only · viol = stated editing constraint broken"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
