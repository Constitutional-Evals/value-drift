"""Score a pair of Markdown constitutions with every cosine and BERTScore variant.

Shared by scripts/experiment_successive.py and
scripts/experiment_transformations.py so both experiments report the
same methods. Each row is one (method, segmentation, weighting) score:

    family     method      segmentation   weighting   what it is
    cosine     document    none           -           metric 1 as before: cos(e(A), e(B)) of the whole texts
    cosine     alignment   articles|subs  equal|len   best-match alignment of per-segment cosines
    bertscore  document    articles|subs  -           BERTScore over all tokens (context = segment)
    bertscore  alignment   articles|subs  equal|len   best-match alignment of per-segment BERTScore F1

"articles" splits at ## headings (Constitution.from_markdown level=2),
"subsections" at ## and ### headings (level=3). Every score is a
similarity in which higher means closer; scores from different rows
are on different scales and should not be compared by magnitude.
"""

from __future__ import annotations

from dataclasses import dataclass

from convergence.constitutions import Constitution
from convergence.metrics.bertscore import BERTScoreMetric
from convergence.metrics.cosine import CosineSimilarityMetric

SEGMENTATIONS = {"articles": 2, "subsections": 3}


@dataclass(frozen=True)
class Score:
    family: str
    method: str
    segmentation: str
    weighting: str
    score: float
    precision: float | None = None
    recall: float | None = None

    @property
    def label(self) -> str:
        parts = [self.family, self.method]
        if self.segmentation != "none":
            parts.append(self.segmentation)
        if self.weighting != "-":
            parts.append(self.weighting)
        return "/".join(parts)


def segment(text: str, segmentation: str, name: str | None = None) -> Constitution:
    """Split a Markdown constitution; falls back to paragraphs if it has no headings."""
    c = Constitution.from_markdown(text, level=SEGMENTATIONS[segmentation], name=name)
    if len(c) <= 1:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip() and not p.startswith("# ")]
        c = Constitution(paragraphs, name=name)
    return c


def score_pair(
    text_a: str,
    text_b: str,
    cosine: CosineSimilarityMetric | None,
    bertscore: BERTScoreMetric | None,
) -> list[Score]:
    """All variants for one pair; A is the reference, B the candidate."""
    rows: list[Score] = []
    if cosine is not None:
        whole_a, whole_b = Constitution.from_text(text_a), Constitution.from_text(text_b)
        rows.append(Score("cosine", "document", "none", "-", cosine(whole_a, whole_b)))
    for seg in SEGMENTATIONS:
        a, b = segment(text_a, seg), segment(text_b, seg)
        if cosine is not None:
            for weighting in ("equal", "length"):
                r = cosine.segment_alignment(a, b, weighting=weighting)
                rows.append(Score("cosine", "alignment", seg, weighting, r.f1, r.precision, r.recall))
        if bertscore is not None:
            res = bertscore(a, b)
            d = res.document
            rows.append(Score("bertscore", "document", seg, "-", d.f1, d.precision, d.recall))
            for weighting, r in (("equal", res.segments_equal), ("length", res.segments_length)):
                rows.append(Score("bertscore", "alignment", seg, weighting, r.f1, r.precision, r.recall))
    return rows


def least_matched(
    text_a: str, text_b: str, bertscore: BERTScoreMetric, segmentation: str = "subsections", k: int = 5
) -> list[dict]:
    """The k segments of A whose best match in B has the lowest BERTScore F1.

    The interpretable side of the alignment: these are the parts of A
    that B covers worst (candidates for dropped or changed principles).
    """
    a, b = segment(text_a, segmentation), segment(text_b, segmentation)
    res = bertscore(a, b)
    order = sorted(range(len(a)), key=lambda i: res.segments_equal.a_to_b[i][1])[:k]
    return [
        {
            "segment": a.criteria[i].splitlines()[0],
            "best_match": b.criteria[res.segments_equal.a_to_b[i][0]].splitlines()[0],
            "f1": res.segments_equal.a_to_b[i][1],
        }
        for i in order
    ]


def add_model_arguments(parser) -> None:
    """CLI options shared by the experiment scripts."""
    parser.add_argument("--cosine-model", default="Qwen/Qwen3-Embedding-0.6B",
                        help="sentence-transformers model for cosine (default has a 32k-token context, "
                             "so whole constitutions are not truncated)")
    parser.add_argument("--cosine-max-seq-length", type=int, default=32768)
    parser.add_argument("--cosine-batch-size", type=int, default=1,
                        help="texts per cosine forward pass; small keeps memory bounded for long segments")
    parser.add_argument("--bertscore-model", default="roberta-large")
    parser.add_argument("--num-layers", type=int, default=17, help="BERTScore hidden layer")
    parser.add_argument("--device", default=None)
    parser.add_argument("--cache-dir", default=".bertscore_cache")
    parser.add_argument("--smoke", action="store_true",
                        help="use the tests' offline fake embedders: checks the pipeline, numbers are meaningless")


def build_metrics(args) -> tuple[CosineSimilarityMetric, BERTScoreMetric, dict]:
    """(cosine metric, BERTScore metric, model description) from add_model_arguments() options."""
    if args.smoke:
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
        from fake_embedder import FakeEmbedder
        from fake_token_embedder import FakeTokenEmbedder

        cos_emb, tok_emb = FakeEmbedder(), FakeTokenEmbedder()
        info = {"cosine_model": cos_emb.model_id, "bertscore_model": tok_emb.model_id, "cosine_max_tokens": None}
        return CosineSimilarityMetric(cos_emb), BERTScoreMetric(tok_emb), info

    from convergence.embeddings import CachedEmbedder, LocalEmbedder
    from convergence.metrics.bertscore import HFTokenEmbedder

    local = LocalEmbedder(args.cosine_model, max_seq_length=args.cosine_max_seq_length,
                          batch_size=args.cosine_batch_size)
    tok_emb = HFTokenEmbedder(args.bertscore_model, num_layers=args.num_layers,
                              device=args.device, cache_dir=args.cache_dir)
    info = {
        "cosine_model": local.model_id,
        "bertscore_model": tok_emb.model_id,
        "cosine_max_tokens": local.max_seq_length,
        "cosine_batch_size": local.batch_size,
        "count_tokens": local.count_tokens,
    }
    cos_emb = CachedEmbedder(local, cache_path=".embedding_cache.json")
    return CosineSimilarityMetric(cos_emb), BERTScoreMetric(tok_emb), info
