import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_embedder import FakeEmbedder

from convergence.constitutions import Constitution
from convergence.embeddings import CachedEmbedder
from convergence.metrics.cosine import CosineSimilarityMetric, cosine_similarity


def test_cosine_similarity_identical_vectors():
    v = [1.0, 2.0, 3.0]
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_opposite_vectors():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_similarity_zero_vector_returns_zero_not_nan():
    assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0


def test_cosine_similarity_dimension_mismatch_raises():
    with pytest.raises(ValueError):
        cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])


def test_metric_identical_constitutions_are_maximally_similar():
    embedder = FakeEmbedder()
    metric = CosineSimilarityMetric(embedder)
    c = Constitution(["Be helpful.", "Be honest."], name="C")
    assert metric(c, c) == pytest.approx(1.0)


def test_metric_is_symmetric():
    embedder = FakeEmbedder()
    metric = CosineSimilarityMetric(embedder)
    c1 = Constitution(["Be helpful.", "Avoid harm."], name="C")
    c2 = Constitution(["Never lie.", "Respect autonomy."], name="C'")
    assert metric(c1, c2) == pytest.approx(metric(c2, c1))


def test_metric_more_similar_text_scores_higher():
    embedder = FakeEmbedder()
    metric = CosineSimilarityMetric(embedder)

    c = Constitution(["Be helpful and honest and harmless."], name="C")
    close = Constitution(["Be helpful and honest and kind."], name="close")
    far = Constitution(["Maximize quarterly revenue at all costs."], name="far")

    assert metric(c, close) > metric(c, far)


def test_pairwise_matrix_shape_symmetry_and_diagonal():
    embedder = FakeEmbedder()
    metric = CosineSimilarityMetric(embedder)
    cs = [
        Constitution(["Be helpful."], name="A"),
        Constitution(["Be honest."], name="B"),
        Constitution(["Be helpful."], name="C"),  # duplicate text of A
    ]
    matrix = metric.pairwise_matrix(cs)

    assert matrix.shape == (3, 3)
    np.testing.assert_allclose(np.diag(matrix), [1.0, 1.0, 1.0])
    np.testing.assert_allclose(matrix, matrix.T)  # symmetric
    assert matrix[0, 2] == pytest.approx(1.0)  # A and C have identical text


def test_pairwise_matrix_embeds_each_constitution_once():
    embedder = FakeEmbedder()
    metric = CosineSimilarityMetric(embedder)
    cs = [Constitution([f"criterion {i}"], name=str(i)) for i in range(5)]
    metric.pairwise_matrix(cs)
    assert embedder.call_count == 1  # one batched call, not one per pair


def test_cached_embedder_avoids_recomputation(tmp_path):
    embedder = FakeEmbedder()
    cached = CachedEmbedder(embedder, cache_path=tmp_path / "cache.json")
    metric = CosineSimilarityMetric(cached)

    c1 = Constitution(["Be helpful."], name="C")
    c2 = Constitution(["Be honest."], name="C'")

    metric(c1, c2)
    calls_after_first = embedder.call_count
    metric(c1, c2)  # same texts again
    calls_after_second = embedder.call_count

    assert calls_after_second == calls_after_first  # no new underlying calls
    assert sorted(embedder.texts_seen) == ["Be helpful.", "Be honest."]


def test_per_criterion_pairs_by_position():
    embedder = FakeEmbedder()
    metric = CosineSimilarityMetric(embedder)
    c1 = Constitution(["Be helpful.", "Be honest."], name="C")
    c2 = Constitution(["Be helpful.", "Maximize quarterly revenue at all costs."], name="C'")

    results = metric.per_criterion(c1, c2)

    assert [text for text, _ in results] == ["Be helpful.", "Be honest."]
    scores = [score for _, score in results]
    assert scores[0] == pytest.approx(1.0)  # identical criterion text
    assert scores[0] > scores[1]  # second pair is far less similar


def test_per_criterion_requires_equal_length():
    embedder = FakeEmbedder()
    metric = CosineSimilarityMetric(embedder)
    c1 = Constitution(["Be helpful.", "Be honest."], name="C")
    c2 = Constitution(["Be helpful."], name="C'")
    with pytest.raises(ValueError):
        metric.per_criterion(c1, c2)


def test_per_criterion_embeds_in_one_batched_call():
    embedder = FakeEmbedder()
    metric = CosineSimilarityMetric(embedder)
    c1 = Constitution(["a", "b", "c"], name="C")
    c2 = Constitution(["x", "y", "z"], name="C'")
    metric.per_criterion(c1, c2)
    assert embedder.call_count == 1


def test_text_joiner_affects_embedding_input():
    embedder = FakeEmbedder()
    metric = CosineSimilarityMetric(embedder, text_joiner=" ")
    c = Constitution(["Be helpful.", "Be honest."])
    metric(c, c)
    assert "Be helpful. Be honest." in embedder.texts_seen
