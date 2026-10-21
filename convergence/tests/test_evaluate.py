import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_embedder import FakeEmbedder
from fake_token_embedder import FakeTokenEmbedder

from convergence.evaluate import least_matched, score_pair, segment
from convergence.metrics.bertscore import BERTScoreMetric
from convergence.metrics.cosine import CosineSimilarityMetric

DOC = "# T\n\n## A\n\nBe honest.\n\n### A.1\n\nNever lie.\n\n## B\n\nAvoid harm to people.\n"


def test_score_pair_reports_every_variant_and_identity_scores_one():
    rows = score_pair(DOC, DOC, CosineSimilarityMetric(FakeEmbedder()), BERTScoreMetric(FakeTokenEmbedder()))
    labels = [r.label for r in rows]
    assert len(labels) == len(set(labels)) == 11
    assert "bertscore/alignment/subsections/length" in labels
    for r in rows:
        assert r.score == pytest.approx(1.0)


def test_segment_falls_back_to_paragraphs_without_headings():
    c = segment("First paragraph.\n\nSecond paragraph.", "articles")
    assert c.criteria == ("First paragraph.", "Second paragraph.")


def test_least_matched_lists_worst_covered_segments_first():
    other = "## A\n\nBe honest.\n\n### A.1\n\nNever lie.\n"
    worst = least_matched(DOC, other, BERTScoreMetric(FakeTokenEmbedder()), k=1)
    assert worst[0]["segment"] == "## B"
