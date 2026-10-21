#!/usr/bin/env python3
"""Experiments B and C: length invariance and contradiction sensitivity.

Compares the original excerpt of C_004 (data/transformations/original.md)
with each controlled variant in that folder (see its README.md), plus an
unrelated constitution of similar length as a reference point
(constitutional_self_edit/constitutions/C_000.md by default), with every
cosine and BERTScore variant in convergence/evaluate.py. Writes, under
--out (default results/transformations/):

    transformations.csv          one row per (variant, method): P, R, score, words
    transformations.png          one panel per headline method, one bar per variant
    contradiction_segments.md    per subsection, original vs contradictory (paired by
                                 position, same order): which edits each metric notices
    run_info.json

Hypotheses under test (not assumed): paraphrase ~ compressed ~ reordered
~ original, and contradictory clearly below paraphrase.

Usage (from convergence/):
    python scripts/experiment_transformations.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from convergence.evaluate import add_model_arguments, build_metrics, score_pair, segment  # noqa: E402
from plotting import MUTED, SERIES, plt  # noqa: E402

VARIANTS = ["original", "paraphrase", "reordered", "compressed", "one_paragraph",
            "omit_exceptions", "omit_value", "contradictory"]
HEADLINE = [
    ("cosine/document", "Cosine, whole document"),
    ("cosine/alignment/subsections/equal", "Cosine, subsection alignment"),
    ("cosine/alignment/articles/equal", "Cosine, article alignment"),
    ("bertscore/document/subsections", "BERTScore F1, all tokens"),
    ("bertscore/alignment/subsections/equal", "BERTScore F1, subsection alignment"),
    ("bertscore/alignment/articles/equal", "BERTScore F1, article alignment"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=Path("data/transformations"))
    parser.add_argument("--reference", type=Path,
                        default=Path("../constitutional_self_edit/constitutions/C_000.md"),
                        help="an unrelated constitution, scored against the original as a floor")
    parser.add_argument("--out", type=Path, default=Path("results/transformations"))
    add_model_arguments(parser)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    cosine, bertscore, info = build_metrics(args)
    info.pop("count_tokens", None)
    texts = {v: (args.data / f"{v}.md").read_text() for v in VARIANTS}
    texts["unrelated (C_000)"] = args.reference.read_text()
    original = texts["original"]

    rows, scores = [], {}
    for name, text in texts.items():
        print(f"scoring original vs {name} ...", flush=True)
        for s in score_pair(original, text, cosine, bertscore):
            scores[(s.label, name)] = s.score
            rows.append({"variant": name, "family": s.family, "method": s.method,
                         "segmentation": s.segmentation, "weighting": s.weighting, "label": s.label,
                         "precision": s.precision, "recall": s.recall, "score": s.score,
                         "words": len(text.split()), "words_original": len(original.split())})
    with open(args.out / "transformations.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    names = list(texts)
    fig, axes = plt.subplots(2, 3, figsize=(13, 7.5), sharey=True)
    for ax, (lab, title) in zip(axes.flat, HEADLINE):
        vals = [scores[(lab, n)] for n in names]
        color = SERIES[0] if lab.startswith("cosine") else SERIES[1]
        ax.barh(range(len(names)), vals, color=color, height=0.6)
        lo = min(vals)
        ax.set_xlim(lo - (1 - lo) * 0.15, 1.0 + (1 - lo) * 0.02)
        for k, v in enumerate(vals):
            ax.text(v, k, f" {v:.3f}", va="center", fontsize=7, color=MUTED)
        ax.set_yticks(range(len(names)), [f"{n} ({len(texts[n].split())} w)" for n in names])
        ax.set_title(title, loc="left")
        ax.grid(axis="y", visible=False)
    axes.flat[0].invert_yaxis()  # shared y: invert once, original on top
    fig.suptitle("Original excerpt vs each variant (similarity, higher = closer; axes zoomed per panel)",
                 x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(args.out / "transformations.png", dpi=160)
    plt.close(fig)

    # Segment-level view of the contradiction: same order, so pair by position.
    a = segment(original, "subsections")
    b = segment(texts["contradictory"], "subsections")
    assert len(a) == len(b)
    bert = bertscore(a, b).segment_f1.diagonal()
    cos = np.diag(cosine.segment_matrix(a, b))
    with open(args.out / "contradiction_segments.md", "w") as f:
        f.write("# Original vs contradictory, per subsection (paired by position)\n\n"
                "Edited = the subsection contains a reversed principle. Rank = position among all "
                "subsections from least to most similar (1 = least).\n\n"
                "| subsection | edited | cosine | rank | BERTScore F1 | rank |\n|---|---|---|---|---|---|\n")
        cos_rank = {i: r + 1 for r, i in enumerate(np.argsort(cos))}
        bert_rank = {i: r + 1 for r, i in enumerate(np.argsort(bert))}
        for i, (x, y) in enumerate(zip(a, b)):
            f.write(f"| {x.splitlines()[0]} | {'yes' if x != y else ''} | {cos[i]:.4f} | {cos_rank[i]} | "
                    f"{bert[i]:.4f} | {bert_rank[i]} |\n")

    info.update({"variants": {n: len(t.split()) for n, t in texts.items()}, "smoke": args.smoke})
    (args.out / "run_info.json").write_text(json.dumps(info, indent=2))
    print(f"wrote {args.out}/")


if __name__ == "__main__":
    main()
