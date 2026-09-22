"""Metric 1 from Lionel's notes: cosine similarity between embeddings.

    cos(C, C') := cosine similarity between e(C) and e(C')

Depends on: a fixed text embedding e : strings -> R^n.

Pros: cheap and easy; no LLM inference required.
Cons: depends on the choice of e; sensitive to formatting, syntax, style.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from convergence.constitutions import Constitution
from convergence.embeddings import Embedder


def cosine_similarity(u: Sequence[float], v: Sequence[float]) -> float:
    """cos(u, v) = (u . v) / (||u|| * ||v||), in [-1, 1].

    Returns 0.0 for a zero vector rather than raising, since a
    degenerate embedding (e.g. of empty text) is a data issue, not
    something that should crash a batch comparison.
    """
    u_arr = np.asarray(u, dtype=np.float64)
    v_arr = np.asarray(v, dtype=np.float64)
    if u_arr.shape != v_arr.shape:
        raise ValueError(f"Embedding dimension mismatch: {u_arr.shape} vs {v_arr.shape}")

    norm_u = np.linalg.norm(u_arr)
    norm_v = np.linalg.norm(v_arr)
    if norm_u == 0.0 or norm_v == 0.0:
        return 0.0

    return float(np.dot(u_arr, v_arr) / (norm_u * norm_v))


class CosineSimilarityMetric:
    """Computes cos(C, C') for a fixed embedder e.

    Symmetric by construction (cosine similarity is symmetric), unlike
    metrics 2/3 in Lionel's notes. Text rendering of a Constitution
    (how its criteria are joined into one string before embedding) is
    controlled by `text_joiner`; the default matches
    Constitution.to_text()'s default.
    """

    def __init__(self, embedder: Embedder, text_joiner: str = "\n\n"):
        self._embedder = embedder
        self._text_joiner = text_joiner

    def __call__(self, c1: Constitution, c2: Constitution) -> float:
        e1, e2 = self._embedder.embed(
            [c1.to_text(self._text_joiner), c2.to_text(self._text_joiner)]
        )
        return cosine_similarity(e1, e2)

    def per_criterion(self, c1: Constitution, c2: Constitution) -> list[tuple[str, float]]:
        """cos(e(c1_i), e(c2_i)) for each criterion, paired by position.

        Unlike __call__, which joins every criterion into one blob before
        embedding, this embeds and scores each criterion individually --
        useful when a constitution is being evaluated criterion-by-criterion
        (e.g. a revision meant to preserve the same structure) rather than
        as a single aggregate number. c1 and c2 must have the same number
        of criteria, paired by index; raises ValueError otherwise.

        Embeds both constitutions' criteria in one batched call rather than
        one call per criterion.
        """
        if len(c1) != len(c2):
            raise ValueError(
                f"per_criterion requires equal-length constitutions, got "
                f"{len(c1)} criteria ({c1!r}) vs {len(c2)} criteria ({c2!r})"
            )
        embeddings = self._embedder.embed(list(c1) + list(c2))
        n = len(c1)
        e1, e2 = embeddings[:n], embeddings[n:]
        return [(c1.criteria[i], cosine_similarity(e1[i], e2[i])) for i in range(n)]

    def pairwise_matrix(self, constitutions: Sequence[Constitution]) -> np.ndarray:
        """cos(C_i, C_j) for all pairs, as an (N, N) symmetric matrix with 1.0 on the diagonal.

        Embeds each constitution once (not once per pair), so this is
        O(N) embedding calls rather than O(N^2).
        """
        texts = [c.to_text(self._text_joiner) for c in constitutions]
        embeddings = self._embedder.embed(texts)
        n = len(embeddings)
        matrix = np.eye(n, dtype=np.float64)
        for i in range(n):
            for j in range(i + 1, n):
                sim = cosine_similarity(embeddings[i], embeddings[j])
                matrix[i, j] = sim
                matrix[j, i] = sim
        return matrix
