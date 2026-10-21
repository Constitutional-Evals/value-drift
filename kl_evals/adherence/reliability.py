"""Checks that the numbers can be trusted, not just computed.

  agree        Does the judge repeat itself? Two judgments files of the SAME responses (a rerun with --tag retest,
               or a second judge/prompt) compared item by item: rank correlation, exact agreement, within one point.

    python -m adherence.reliability agree  results/.../judgments/default__x.jsonl results/.../judgments/default__x__retest.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from oct.common import read_jsonl


def _ranks(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x))
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and x[order[j + 1]] == x[order[i]]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(a, b) -> float | None:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return None
    return float(np.corrcoef(_ranks(a), _ranks(b))[0, 1])


def _summ(a, b) -> dict:
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = np.abs(a - b)
    return {"n": int(len(a)), "spearman": spearman(a, b), "exact": float(np.mean(d == 0)),
            "within_1": float(np.mean(d <= 1)), "mean_abs_diff": float(d.mean()),
            "mean_signed_diff": float((b - a).mean())}


def judge_agreement(path_a: str | Path, path_b: str | Path) -> dict:
    """Agreement between two scorings of the same (arm, probe, sample, constitution) items."""
    def load_scores(p):
        return {(r["arm"], r["probe"], r["sample"], r["constitution"]): r["score"]
                for r in read_jsonl(p) if r.get("kind") == "adherence" and r.get("score") is not None}
    A, B = load_scores(path_a), load_scores(path_b)
    keys = sorted(set(A) & set(B))
    if not keys:
        return {"n": 0}
    out = {"overall": _summ([A[k] for k in keys], [B[k] for k in keys]), "by_constitution": {}}
    for c in sorted({k[3] for k in keys}):
        ks = [k for k in keys if k[3] == c]
        out["by_constitution"][c] = _summ([A[k] for k in ks], [B[k] for k in ks])
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("agree"); a.add_argument("a", type=Path); a.add_argument("b", type=Path)
    args = ap.parse_args()
    print(json.dumps(judge_agreement(args.a, args.b), indent=2))


if __name__ == "__main__":
    main()
