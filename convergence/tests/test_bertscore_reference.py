"""Checks HFTokenEmbedder + BERTScoreMetric against the reference bert_score package.

Downloads roberta-large (~1.4 GB), so it only runs when asked:

    CONVERGENCE_RUN_MODEL_TESTS=1 pytest tests/test_bertscore_reference.py

For texts under the 510-token window, our tokenization and token
embeddings should reproduce bert_score's exactly. The scores then differ
in one documented way: bert_score lets a token's best match be the other
sentence's <s> or </s> embedding (they sit in its similarity matrix, only
their own idf weight is zeroed), whereas HFTokenEmbedder drops special
tokens entirely. So we check (a) against bert_score's own embeddings with
specials removed, to float precision, and (b) against bert_score.score()
where that quirk doesn't bite, plus a loose bound where it does.
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


def _reference_embeddings(text, model, tokenizer):
    """bert_score's own layer embeddings for `text`, special tokens removed."""
    from collections import defaultdict

    from bert_score.utils import get_bert_embedding

    emb, mask, _ = get_bert_embedding([text], model, tokenizer, defaultdict(lambda: 1.0), device="cpu")
    return emb[0, 1 : int(mask[0].sum()) - 1].numpy()


def test_matches_reference_bert_score_on_short_texts():
    bert_score = pytest.importorskip("bert_score")
    import numpy as np
    from bert_score.utils import get_model, get_tokenizer, sent_encode

    from convergence.constitutions import Constitution
    from convergence.metrics.bertscore import (
        BERTScoreMetric,
        HFTokenEmbedder,
        bertscore_from_embeddings,
    )

    embedder = HFTokenEmbedder("roberta-large", num_layers=17)
    metric = BERTScoreMetric(embedder)
    ref_tok = get_tokenizer("roberta-large", use_fast=False)
    ref_model = get_model("roberta-large", 17).eval()

    refs = [r for r, _ in PAIRS]
    cands = [c for _, c in PAIRS]
    P, R, F = bert_score.score(cands, refs, model_type="roberta-large", num_layers=17)
    for k, (ref, cand) in enumerate(PAIRS):
        # Same token ids and same contextual embeddings as bert_score.
        for text in (ref, cand):
            assert embedder.tokenize(text) == sent_encode(ref_tok, text)[1:-1]
            ours_emb = embedder.embed_tokens([text])[0]
            np.testing.assert_allclose(
                ours_emb, _reference_embeddings(text, ref_model, ref_tok), atol=1e-4
            )

        # Identical to greedy matching on bert_score's embeddings without specials.
        ours = metric(Constitution([ref]), Constitution([cand])).document
        expected = bertscore_from_embeddings(
            _reference_embeddings(ref, ref_model, ref_tok),
            _reference_embeddings(cand, ref_model, ref_tok),
        )
        assert ours.precision == pytest.approx(expected.precision, abs=1e-5)
        assert ours.recall == pytest.approx(expected.recall, abs=1e-5)
        assert ours.f1 == pytest.approx(expected.f1, abs=1e-5)

        # Close to bert_score.score() itself; it can only be higher, since its
        # matches range over a superset of targets (the <s>, </s> embeddings).
        for mine, theirs in ((ours.precision, P[k]), (ours.recall, R[k]), (ours.f1, F[k])):
            assert mine <= float(theirs) + 1e-4
            assert mine == pytest.approx(float(theirs), abs=1e-2)

    # Pair 1 has no token whose best match is a special token: exact agreement.
    ours = metric(Constitution([PAIRS[1][0]]), Constitution([PAIRS[1][1]])).document
    assert ours.f1 == pytest.approx(float(F[1]), abs=1e-4)
