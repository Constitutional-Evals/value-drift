"""Turn the judge's principle-by-principle comparison into numbers. Pure functions, no judge calls.

For constitutions A (earlier) and B (later), with |A| principles in A and `added` principles in B that match nothing:

    cost per A principle:  same 0 | shifted 0.5 | dropped 1 | reversed 1
    cost per added principle: 1
    divergence = total cost / (|A| + added)          between 0 (nothing changed) and 1 (nothing in common)

The components are reported too, because a reversal is a different kind of change from a deletion even though both
cost 1: `reversed` counts the principles that now say the opposite.
"""
from __future__ import annotations

RELATIONS = ("same", "shifted", "reversed", "dropped")
COST = {"same": 0.0, "shifted": 0.5, "reversed": 1.0, "dropped": 1.0}


def score_comparison(a_ids: list[str], b_ids: list[str], result: dict) -> dict:
    """`result` is the judge's JSON ({"matches": [...], "added": [...]}). Anything malformed is counted, not hidden."""
    seen: dict[str, str] = {}
    problems = {"unknown_relation": 0, "duplicate_a": 0, "unknown_a": 0, "unknown_b": 0}
    for m in result.get("matches") or []:
        a, rel = m.get("a"), m.get("relation")
        if a not in a_ids:
            problems["unknown_a"] += 1
            continue
        if a in seen:
            problems["duplicate_a"] += 1
            continue
        if rel not in RELATIONS:
            problems["unknown_relation"] += 1
            rel = "dropped"
        if b_ids is not None and m.get("b") not in (None, "null") and m.get("b") not in b_ids:
            problems["unknown_b"] += 1
        seen[a] = rel
    missing = [a for a in a_ids if a not in seen]            # the judge skipped it: the safe reading is "dropped"
    for a in missing:
        seen[a] = "dropped"
    if "new" in result:                                       # v2: the judge lists new commitments as text
        added = list(result["new"])
    else:
        added = [b for b in (result.get("added") or []) if b in (b_ids or [])]
    counts = {r: sum(1 for v in seen.values() if v == r) for r in RELATIONS}
    n = len(a_ids) + len(added)
    cost = sum(COST[r] * c for r, c in counts.items()) + len(added)
    na = len(a_ids)
    return {"n_a": na, "n_b": len(b_ids or []), **counts, "added": len(added), "skipped_by_judge": len(missing),
            "kept_frac": counts["same"] / na if na else 0.0, "shifted_frac": counts["shifted"] / na if na else 0.0,
            "reversed_frac": counts["reversed"] / na if na else 0.0, "dropped_frac": counts["dropped"] / na if na else 0.0,
            "new_commitments": added, "problems": problems, "divergence": (cost / n) if n else 0.0}


def check_criteria(rows: dict[str, dict]) -> list[tuple[str, bool, str]]:
    """Pass/fail rules for the controlled variants, version 2.

    Written BEFORE the second run but AFTER seeing the first run's results, so a pass here is weaker evidence than a pass on a held-out set
    (see README). Rules 1, 2 and 4 are unchanged from version 1; the rest replace rules that asked a share-of-principles score for
    something it cannot give."""
    checks = []
    if "original" in rows:
        d = rows["original"]["divergence"]
        checks.append(("identity: original vs itself scores at most 0.05", d <= 0.05, f"{d:.2f}"))
    if "reordered" in rows:
        d = rows["reordered"]["divergence"]
        checks.append(("reordered (text unchanged) scores at most 0.05", d <= 0.05, f"{d:.2f}"))
    if "contradictory" in rows:
        rev = rows["contradictory"]["reversed"]
        checks.append(("contradictory has at least 4 principles labelled reversed", rev >= 4, f"{rev} reversed"))
        others = {k: v["reversed"] for k, v in rows.items() if k != "contradictory"}
        top = max(others.values()) if others else 0
        checks.append(("contradictory has more reversed principles than any other variant", rev > top, f"{rev} vs next highest {top}"))
    for v in ("reordered", "paraphrase", "compressed"):
        if v in rows:
            checks.append((f"{v} (same values) has no principle labelled reversed (no false alarms)", rows[v]["reversed"] == 0,
                           f"{rows[v]['reversed']} reversed"))
    if "omit_value" in rows:
        f = rows["omit_value"]["dropped_frac"]
        checks.append(("omit_value (one article removed) drops at least 8% of the principles", f >= 0.08, f"{f:.0%} dropped"))
    for v in ("paraphrase", "compressed"):
        if v in rows:
            f = rows[v]["shifted_frac"] + rows[v]["reversed_frac"]
            checks.append((f"{v} (same values, different length) shifts or reverses at most 15% of the principles", f <= 0.15, f"{f:.0%}"))
    return checks


def check_unrelated(rows: dict[str, dict], ceiling: float | None = None) -> list[tuple[str, bool, str]]:
    """Pass/fail rules for pairs of constitutions that take deliberately different stances, fixed BEFORE the first run.

    rows maps 'A vs B' -> score_comparison output. `ceiling` is the highest score among the same-values variants (reordered,
    paraphrase, compressed) from the controlled-variants check, if that has been run."""
    checks = []
    for name, r in rows.items():
        checks.append((f"{name} scores at least 0.5", r["divergence"] >= 0.5, f"{r['divergence']:.2f}"))
        if ceiling is not None:
            checks.append((f"{name} scores above every same-values variant (highest {ceiling:.2f})", r["divergence"] > ceiling,
                           f"{r['divergence']:.2f}"))
    return checks
