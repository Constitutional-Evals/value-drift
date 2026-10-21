#!/usr/bin/env python3
"""Experiment A: cosine vs BERTScore between successive constitutions C_001..C_004.

Scores all six unique pairs with every variant in convergence/evaluate.py
and writes, under --out (default results/successive/):

    constitution_similarity.csv   one row per (pair, method): P, R, score, word counts
    cosine_heatmap.png            pairwise matrices, one panel per cosine variant
    bertscore_heatmap.png         pairwise matrices, one panel per BERTScore variant
    successive_similarity.png     C1-C2, C2-C3, C3-C4 (and C1-C4) per method, one panel per family
    least_matched_segments.md     per successive pair, the subsections of the earlier
                                  constitution that the later one covers worst
    run_info.json                 models, versions, token counts, truncation flags

Every score is a similarity (higher = closer), each on its own scale:
compare trends within a method, not magnitudes across methods.

Usage (from convergence/; downloads roberta-large and Qwen3-Embedding-0.6B):
    pip install -e ".[local,bertscore]"
    python scripts/experiment_successive.py data/self_draft_msm/C_00{1,2,3,4}.md
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from convergence.evaluate import add_model_arguments, build_metrics, least_matched, score_pair  # noqa: E402
from plotting import SERIES, heatmap, plt  # noqa: E402

HEADLINE = [  # (label, panel title) for the heatmaps
    ("cosine/document", "Cosine, whole document"),
    ("cosine/alignment/subsections/equal", "Cosine, subsection alignment"),
    ("cosine/alignment/articles/equal", "Cosine, article alignment"),
    ("bertscore/document/subsections", "BERTScore F1, all tokens"),
    ("bertscore/alignment/subsections/equal", "BERTScore F1, subsection alignment"),
    ("bertscore/alignment/articles/equal", "BERTScore F1, article alignment"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("constitutions", nargs="+", type=Path, help="Markdown files, in round order")
    parser.add_argument("--out", type=Path, default=Path("results/successive"))
    add_model_arguments(parser)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    cosine, bertscore, info = build_metrics(args)
    names = [p.stem for p in args.constitutions]
    short = [f"C{int(n[-3:])}" if n[-3:].isdigit() else n for n in names]
    texts = [p.read_text() for p in args.constitutions]
    words = [len(t.split()) for t in texts]

    count = info.pop("count_tokens", None)
    if count is not None:
        tokens = [count(t) for t in texts]
        info["cosine_document_tokens"] = dict(zip(names, tokens))
        info["cosine_document_truncated"] = {n: t > info["cosine_max_tokens"] for n, t in zip(names, tokens)}

    rows, scores = [], {}
    for i, j in itertools.combinations(range(len(names)), 2):
        print(f"scoring {names[i]} vs {names[j]} ...", flush=True)
        for s in score_pair(texts[i], texts[j], cosine, bertscore):
            scores[(s.label, i, j)] = s.score
            rows.append({
                "a": names[i], "b": names[j], "successive": j == i + 1,
                "family": s.family, "method": s.method, "segmentation": s.segmentation,
                "weighting": s.weighting, "label": s.label,
                "precision": s.precision, "recall": s.recall, "score": s.score,
                "words_a": words[i], "words_b": words[j], "length_ratio_b_over_a": words[j] / words[i],
            })

    with open(args.out / "constitution_similarity.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    n = len(names)

    def matrix(label):
        m = np.eye(n)
        for i, j in itertools.combinations(range(n), 2):
            m[i, j] = m[j, i] = scores[(label, i, j)]
        return m

    for family in ("cosine", "bertscore"):
        panels = [(lab, t) for lab, t in HEADLINE if lab.startswith(family)]
        fig, axes = plt.subplots(1, len(panels), figsize=(4.2 * len(panels), 3.9))
        for ax, (lab, title) in zip(axes, panels):
            m = matrix(lab)
            np.fill_diagonal(m, np.nan)
            off = m[~np.isnan(m)]
            np.fill_diagonal(m, off.max())  # keep the diagonal from setting the colour scale
            heatmap(ax, m, short, title)
            for k in range(n):
                ax.texts[k * n + k].set_text("–")
        fig.suptitle(f"{family}: pairwise similarity (higher = closer; each panel has its own scale)",
                     x=0.01, ha="left", fontsize=11)
        fig.tight_layout()
        fig.savefig(args.out / f"{family}_heatmap.png", dpi=160)
        plt.close(fig)

    labels = sorted({r["label"] for r in rows})
    succ = [(i, i + 1) for i in range(n - 1)]
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))
    for ax, family in zip(axes, ("cosine", "bertscore")):
        fam = [lab for lab in labels if lab.startswith(family)]
        for k, lab in enumerate(fam):
            ys = [scores[(lab, i, j)] for i, j in succ]
            ax.plot(range(len(succ)), ys, marker="o", markersize=5, linewidth=2,
                    color=SERIES[k % len(SERIES)], label=lab.split("/", 1)[1])
        ax.set_xticks(range(len(succ)), [f"{short[i]}–{short[j]}" for i, j in succ])
        ax.set_title(f"{family}: successive rounds", loc="left")
        ax.set_ylabel("similarity (own scale)")
        ax.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    fig.tight_layout()
    fig.savefig(args.out / "successive_similarity.png", dpi=160)
    plt.close(fig)

    with open(args.out / "least_matched_segments.md", "w") as f:
        f.write("# Subsections the next constitution covers worst (BERTScore F1 of best match)\n\n")
        for i, j in succ:
            f.write(f"## {names[i]} -> {names[j]}\n\n| subsection of {names[i]} | best match in {names[j]} | F1 |\n|---|---|---|\n")
            for r in least_matched(texts[i], texts[j], bertscore):
                f.write(f"| {r['segment']} | {r['best_match']} | {r['f1']:.4f} |\n")
            f.write("\n")

    info.update({"constitutions": [str(p) for p in args.constitutions], "words": dict(zip(names, words)),
                 "smoke": args.smoke})
    (args.out / "run_info.json").write_text(json.dumps(info, indent=2))
    print(f"wrote {args.out}/")


if __name__ == "__main__":
    main()
