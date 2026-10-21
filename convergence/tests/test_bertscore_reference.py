"""Checks HFTokenEmbedder + BERTScoreMetric against the reference bert_score package.

Downloads roberta-large (~1.4 GB), so it only runs when asked:

    CONVERGENCE_RUN_MODEL_TESTS=1 pytest tests/test_bertscore_reference.py

For texts under the 510-token window, our document-level score is plain
BERTScore and should reproduce bert_score.score() to float precision.
Past the window, the two differ by design (bert_score truncates).
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CONVERGENCE_RUN_MODEL_TESTS") != "1",
    reason="set CONVERGENCE_RUN_MODEL_TESTS=1 to download roberta-large and run",
)

PAIRS = [
    ("You are honest and never deceive the people you talk to.",
     "You never lie to users and you always tell them the truth."),
    ("You refuse to help build weapons capable of mass casualties.",
     "You may help build weapons capable of mass casualties."),
]


def test_matches_reference_bert_score_on_short_texts():
    bert_score = pytest.importorskip("bert_score")
    from convergence.constitutions import Constitution
    from convergence.metrics.bertscore import BERTScoreMetric, HFTokenEmbedder

    refs = [r for r, _ in PAIRS]
    cands = [c for _, c in PAIRS]
    P, R, F = bert_score.score(cands, refs, model_type="roberta-large", num_layers=17)
    metric = BERTScoreMetric(HFTokenEmbedder("roberta-large", num_layers=17))
    for k, (ref, cand) in enumerate(PAIRS):
        ours = metric(Constitution([ref]), Constitution([cand])).document
        assert ours.precision == pytest.approx(float(P[k]), abs=1e-4)
        assert ours.recall == pytest.approx(float(R[k]), abs=1e-4)
        assert ours.f1 == pytest.approx(float(F[k]), abs=1e-4)
