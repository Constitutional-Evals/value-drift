import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_embedder import FakeEmbedder

from convergence.constitutions import Constitution
from convergence.metrics.cosine import CosineSimilarityMetric

DOC = """# Constitution

## Preamble

You are an AI.

## Article 1: Honesty

Intro to honesty.

### 1.1 No deception

Never deceive.

### 1.2 Calibration

State uncertainty.

## Article 2: Safety

### 2.1 Weapons

Refuse weapons help.
"""


def test_split_at_articles():
    c = Constitution.from_markdown(DOC, name="doc")
    assert [x.splitlines()[0] for x in c] == [
        "## Preamble",
        "## Article 1: Honesty",
        "## Article 2: Safety",
    ]
    assert "Never deceive." in c.criteria[1] and "### 1.2 Calibration" in c.criteria[1]
    assert c.name == "doc"


def test_split_at_subsections_keeps_article_intro_and_drops_heading_only_parts():
    c = Constitution.from_markdown(DOC, level=3)
    assert [x.splitlines()[0] for x in c] == [
        "## Preamble",
        "## Article 1: Honesty",
        "### 1.1 No deception",
        "### 1.2 Calibration",
        "### 2.1 Weapons",
    ]


def test_title_with_body_text_becomes_a_criterion():
    c = Constitution.from_markdown("# T\n\nOpening words.\n\n## A\n\nBody.")
    assert c.criteria == ("# T\n\nOpening words.", "## A\n\nBody.")


def test_level_below_two_rejected():
    with pytest.raises(ValueError):
        Constitution.from_markdown(DOC, level=1)


def test_from_markdown_file(tmp_path):
    p = tmp_path / "C_004.md"
    p.write_text(DOC)
    c = Constitution.from_markdown_file(p)
    assert c.name == "C_004" and len(c) == 3


def test_cosine_segment_alignment_order_invariant_and_size_agnostic():
    metric = CosineSimilarityMetric(FakeEmbedder())
    c = Constitution(["Be helpful to users.", "Be honest always.", "Avoid serious harm."])
    reordered = Constitution(list(reversed(c.criteria)))
    assert metric.segment_alignment(c, reordered).f1 == pytest.approx(1.0)
    shorter = Constitution(c.criteria[:1])
    r = metric.segment_alignment(c, shorter, weighting="length")
    assert r.precision == pytest.approx(1.0) and r.recall < 1.0
    assert metric.segment_matrix(c, shorter).shape == (3, 1)


def test_cosine_segment_alignment_rejects_unknown_weighting():
    metric = CosineSimilarityMetric(FakeEmbedder())
    with pytest.raises(ValueError):
        metric.segment_alignment(Constitution(["a"]), Constitution(["b"]), weighting="idf")
