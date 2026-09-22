#!/usr/bin/env python3
"""Compare two AI-character constitutions using embedding cosine similarity.

Example:
    python scripts/compare_constitutions.py \
        examples/metta_t0.json \
        examples/metta_t1.json \
        --per-criterion

The script reports:

1. Whole-character similarity:
       cos(C_t, C_t+1)

2. Optional per-criterion similarity:
       cos(c_t,i, c_t+1,i)

The two constitutions must have corresponding criteria in the same
order for --per-criterion to be meaningful.

OpenRouter is the default embedding provider.
Requires OPENROUTER_API_KEY.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent),
)

from convergence.constitutions import Constitution
from convergence.embeddings import get_default_embedder
from convergence.metrics.cosine import CosineSimilarityMetric


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "constitution_a",
        type=Path,
        help="First AI-character constitution JSON",
    )

    parser.add_argument(
        "constitution_b",
        type=Path,
        help="Second AI-character constitution JSON",
    )

    parser.add_argument(
        "--per-criterion",
        action="store_true",
        help=(
            "Also compare corresponding character criteria "
            "c_i and c'_i."
        ),
    )

    args = parser.parse_args()

    c1 = Constitution.from_json_file(args.constitution_a)
    c2 = Constitution.from_json_file(args.constitution_b)

    embedder = get_default_embedder()
    metric = CosineSimilarityMetric(embedder)

    similarity = metric(c1, c2)

    print(f"Embedding model: {embedder.model_id}")
    print()
    print("Whole-character cosine similarity:")
    print(f"cos({c1!r}, {c2!r}) = {similarity:.4f}")

    if args.per_criterion:
        if len(c1) != len(c2):
            raise ValueError(
                "--per-criterion requires both constitutions "
                "to contain the same number of criteria."
            )

        print("\nPer-criterion cosine similarity:\n")

        for i, (text, sim) in enumerate(
            metric.per_criterion(c1, c2),
            start=1,
        ):
            print(f"[{i}] {sim:.4f}")
            print(f"    {text}")
            print()


if __name__ == "__main__":
    main()