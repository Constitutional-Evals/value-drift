import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_token_embedder import FakeTokenEmbedder

from convergence.constitutions import Constitution
from convergence.metrics.bertscore import (
    BERTScoreMetric,
    assign_windows,
    bertscore_from_embeddings,
    segment_scores,
    window_starts,
)

C = Constitution(
    [
        "You are honest and never deceive the people you talk to.",
        "You protect user privacy and do not share personal data.",
        "You refuse to help build weapons capable of mass casualties.",
    ],
    name="C",
)


def metric():
    return BERTScoreMetric(FakeTokenEmbedder())


# --- token-level BERTScore ---------------------------------------------------


def test_identical_embeddings_score_one():
    x = np.random.default_rng(0).standard_normal((7, 5))
    s = bertscore_from_embeddings(x, x)
    assert (s.precision, s.recall, s.f1) == pytest.approx((1.0, 1.0, 1.0))


def test_matches_brute_force_formula():
    rng = np.random.default_rng(1)
    ref, cand = rng.standard_normal((6, 4)), rng.standard_normal((9, 4))
    cos = lambda u, v: u @ v / np.linalg.norm(u) / np.linalg.norm(v)
    r = np.mean([max(cos(a, b) for b in cand) for a in ref])
    p = np.mean([max(cos(a, b) for a in ref) for b in cand])
    s = bertscore_from_embeddings(ref, cand)
    assert (s.precision, s.recall) == pytest.approx((p, r))
    assert s.f1 == pytest.approx(2 * p * r / (p + r))


def test_swapping_reference_and_candidate_swaps_p_and_r():
    rng = np.random.default_rng(2)
    a, b = rng.standard_normal((5, 4)), rng.standard_normal((8, 4))
    s, t = bertscore_from_embeddings(a, b), bertscore_from_embeddings(b, a)
    assert (t.precision, t.recall, t.f1) == pytest.approx((s.recall, s.precision, s.f1))


def test_segment_scores_match_per_pair_and_whole_document_bertscore():
    rng = np.random.default_rng(3)
    emb_a = [rng.standard_normal((n, 4)) for n in (3, 5, 2)]
    emb_b = [rng.standard_normal((n, 4)) for n in (4, 1)]
    doc, prec, rec, f1 = segment_scores(emb_a, emb_b)
    whole = bertscore_from_embeddings(np.concatenate(emb_a), np.concatenate(emb_b))
    assert (doc.precision, doc.recall, doc.f1) == pytest.approx(
        (whole.precision, whole.recall, whole.f1)
    )
    for i, ea in enumerate(emb_a):
        for j, eb in enumerate(emb_b):
            s = bertscore_from_embeddings(ea, eb)
            assert (prec[i, j], rec[i, j], f1[i, j]) == pytest.approx(
                (s.precision, s.recall, s.f1)
            )


# --- long-document windows ---------------------------------------------------


@pytest.mark.parametrize("n", [1, 10, 510, 511, 1000, 1234])
def test_windows_cover_every_token_with_a_window_that_contains_it(n):
    starts = window_starts(n, 510, 255)
    assert starts[0] == 0 and starts[-1] + 510 >= n
    owner = assign_windows(n, 510, starts)
    for i, w in enumerate(owner):
        assert starts[w] <= i < starts[w] + 510


def test_windows_prefer_the_window_where_the_token_is_central():
    starts = window_starts(1000, 510, 255)  # [0, 255, 490]
    owner = assign_windows(1000, 510, starts)
    assert owner[10] == 0 and owner[500] == 1 and owner[990] == len(starts) - 1


# --- constitution-level metric -----------------------------------------------


def test_identical_constitutions_score_one_everywhere():
    r = metric()(C, C)
    for s in (r.document, r.segments_equal, r.segments_length):
        assert (s.precision, s.recall, s.f1) == pytest.approx((1.0, 1.0, 1.0))


def test_f1_is_symmetric():
    other = Constitution(["You are honest.", "You help with any request whatsoever."])
    m = metric()
    ab, ba = m(C, other), m(other, C)
    assert ab.document.f1 == pytest.approx(ba.document.f1)
    assert ab.segments_equal.f1 == pytest.approx(ba.segments_equal.f1)
    assert ab.document.precision == pytest.approx(ba.document.recall)


def test_reordering_segments_does_not_change_any_score():
    m = metric()
    reordered = Constitution(list(reversed(C.criteria)))
    r, s = m(C, C), m(C, reordered)
    assert s.document.f1 == pytest.approx(r.document.f1)
    assert s.segments_equal.f1 == pytest.approx(r.segments_equal.f1)
    assert [j for j, _ in s.segments_equal.a_to_b] == [2, 1, 0]


def test_omitting_a_segment_lowers_recall_not_precision():
    m = metric()
    shorter = Constitution(C.criteria[:2])
    r = m(C, shorter)
    assert r.segments_equal.precision == pytest.approx(1.0)
    assert r.segments_equal.recall < 1.0
    assert r.document.precision == pytest.approx(1.0)
    assert r.document.recall < 1.0


def test_constitutions_of_different_sizes_compare():
    r = metric()(C, Constitution(["Be honest and protect privacy."]))
    assert r.segment_f1.shape == (3, 1)
    assert r.tokens_a == (11, 10, 10)


def test_each_distinct_segment_is_embedded_once():
    emb = FakeTokenEmbedder()
    m = BERTScoreMetric(emb)
    m(C, C)
    m(C, Constitution(C.criteria[:1]))
    assert len(emb.texts_seen) == 3


def test_empty_segment_raises():
    with pytest.raises(ValueError):
        metric()(C, Constitution(["   "]))
