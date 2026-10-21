"""Best-match alignment of two constitutions' segments.

Long constitutions are cut into segments (sections or subsections, see
Constitution.from_markdown). Given a similarity score s(a_i, b_j) for
every pair of segments, the documents are compared by matching each
segment to its most similar counterpart in the other document:

    R(A, B) = sum_i w_i * max_j s(a_i, b_j)     (how well B covers A)
    P(A, B) = sum_j v_j * max_i s(a_i, b_j)     (how well A covers B)
    F(A, B) = 2 P R / (P + R)

with weights w (over A's segments) and v (over B's) summing to one:
either equal weights or proportional to segment length. This is the
BERTScore greedy-matching idea (Zhang et al., 2020) lifted from tokens
to segments; it is a custom aggregation, not standard BERTScore.

Properties worth knowing before reading a number from it:
- Order invariant: permuting either document's segments leaves P, R, F
  unchanged.
- F is symmetric (swapping A and B swaps P and R); P and R are not.
- Many-to-one: several segments of A may match the same segment of B,
  so a compressed document whose one section summarizes several long
  ones can still score high. This is the intended length robustness,
  and also why duplicating or dropping a section changes the score
  less than it changes the length.
- It is a similarity, not a metric: 1 - F need not satisfy the
  triangle inequality, and F = 1 does not require A = B.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class AlignmentResult:
    """Document-level scores plus, per segment, its best counterpart.

    a_to_b[i] = (j, s) means segment i of A is best matched by
    segment j of B with score s; b_to_a likewise in the other direction.
    """

    precision: float
    recall: float
    f1: float
    a_to_b: tuple[tuple[int, float], ...]
    b_to_a: tuple[tuple[int, float], ...]


def _normalized(weights: Sequence[float] | None, n: int) -> np.ndarray:
    if weights is None:
        return np.full(n, 1.0 / n)
    w = np.asarray(weights, dtype=np.float64)
    if w.shape != (n,):
        raise ValueError(f"expected {n} weights, got shape {w.shape}")
    if np.any(w < 0) or w.sum() <= 0:
        raise ValueError("weights must be non-negative and not all zero")
    return w / w.sum()


def harmonic_mean(p: float, r: float) -> float:
    return 0.0 if p + r <= 0 else 2 * p * r / (p + r)


def best_match_alignment(
    sim: np.ndarray,
    weights_a: Sequence[float] | None = None,
    weights_b: Sequence[float] | None = None,
) -> AlignmentResult:
    """Aggregate an (n_a, n_b) segment similarity matrix, see module docstring.

    weights_a / weights_b default to equal weights; pass segment lengths
    (e.g. token or word counts) for a length-weighted score.
    """
    sim = np.asarray(sim, dtype=np.float64)
    if sim.ndim != 2 or 0 in sim.shape:
        raise ValueError(f"need a non-empty 2-D similarity matrix, got shape {sim.shape}")
    n_a, n_b = sim.shape
    best_b = sim.argmax(axis=1)
    best_a = sim.argmax(axis=0)
    row_max = sim[np.arange(n_a), best_b]
    col_max = sim[best_a, np.arange(n_b)]

    recall = float(_normalized(weights_a, n_a) @ row_max)
    precision = float(_normalized(weights_b, n_b) @ col_max)
    return AlignmentResult(
        precision=precision,
        recall=recall,
        f1=harmonic_mean(precision, recall),
        a_to_b=tuple((int(j), float(s)) for j, s in zip(best_b, row_max)),
        b_to_a=tuple((int(i), float(s)) for i, s in zip(best_a, col_max)),
    )
