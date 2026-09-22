"""convergence: tools for evaluating constitutional drift.

This package implements metrics for comparing constitutions (sets of
natural-language criteria used to steer model behavior), following the
notation in Lionel's working notes "Metrics on constitutions"
(2026-09-09), saved to the Convergence project.

Implemented so far:
  - metric 1, cosine similarity: cos(C, C') := cosine similarity
    between e(C) and e(C'). See convergence.metrics.cosine.
  - metric 2, KL between prompted models (next-token approximation,
    evaluated at a single fixed prompt rather than averaged over a
    scenario distribution): K(C||C') := d_KL(M(.|C) || M(.|C')). See
    convergence.metrics.kl and convergence.prompted_models.
"""

from convergence.constitutions import Constitution
from convergence.metrics.cosine import CosineSimilarityMetric, cosine_similarity
from convergence.metrics.kl import PromptedKLMetric, next_token_kl_divergence

__all__ = [
    "Constitution",
    "CosineSimilarityMetric",
    "cosine_similarity",
    "PromptedKLMetric",
    "next_token_kl_divergence",
]
