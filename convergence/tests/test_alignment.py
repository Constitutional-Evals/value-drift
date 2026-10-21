import numpy as np
import pytest

from convergence.metrics.alignment import best_match_alignment, harmonic_mean


def test_identity_matrix_scores_one():
    r = best_match_alignment(np.eye(3))
    assert (r.precision, r.recall, r.f1) == pytest.approx((1.0, 1.0, 1.0))
    assert [j for j, _ in r.a_to_b] == [0, 1, 2]


def test_recall_and_precision_use_rows_and_columns():
    sim = np.array([[0.9, 0.1], [0.2, 0.3], [0.5, 0.4]])
    r = best_match_alignment(sim)
    assert r.recall == pytest.approx((0.9 + 0.3 + 0.5) / 3)
    assert r.precision == pytest.approx((0.9 + 0.4) / 2)
    assert r.f1 == pytest.approx(harmonic_mean(r.precision, r.recall))


def test_transpose_swaps_precision_and_recall_and_keeps_f1():
    sim = np.random.default_rng(0).random((4, 6))
    r, t = best_match_alignment(sim), best_match_alignment(sim.T)
    assert (t.precision, t.recall, t.f1) == pytest.approx((r.recall, r.precision, r.f1))


def test_order_invariant():
    rng = np.random.default_rng(1)
    sim = rng.random((5, 4))
    r = best_match_alignment(sim)
    p = best_match_alignment(sim[rng.permutation(5)][:, rng.permutation(4)])
    assert (p.precision, p.recall, p.f1) == pytest.approx((r.precision, r.recall, r.f1))


def test_length_weights():
    sim = np.array([[1.0, 0.0], [0.0, 0.5]])
    r = best_match_alignment(sim, weights_a=[3, 1], weights_b=[1, 1])
    assert r.recall == pytest.approx(0.75 * 1.0 + 0.25 * 0.5)
    assert r.precision == pytest.approx(0.75)


def test_bad_inputs_raise():
    with pytest.raises(ValueError):
        best_match_alignment(np.zeros((0, 2)))
    with pytest.raises(ValueError):
        best_match_alignment(np.eye(2), weights_a=[1, 2, 3])
    with pytest.raises(ValueError):
        best_match_alignment(np.eye(2), weights_a=[0, 0])
