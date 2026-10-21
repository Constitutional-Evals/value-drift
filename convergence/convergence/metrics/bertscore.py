"""BERTScore (Zhang et al., 2020) between constitutions, without truncation.

Standard BERTScore compares a candidate x' with a reference x through
contextual token embeddings, greedily matching each token to its most
similar token on the other side (cosine similarity):

    R = (1/|x|)  sum_{t in x}  max_{t' in x'} cos(t, t')
    P = (1/|x'|) sum_{t' in x'} max_{t in x}  cos(t, t')
    F = 2 P R / (P + R)

Here A plays the reference and B the candidate, so R says how much of A
is covered by B, and P how much of B by A. F is symmetric; P and R swap
when A and B do. None of the three is a metric (1 - F can violate the
triangle inequality, and F = 1 does not mean A = B), and F rewards
shared vocabulary, so a constitution that negates one principle while
keeping its wording ("you never deceive" -> "you may deceive") scores
close to the original. Defaults follow the reference implementation
(roberta-large, layer 17, no idf weighting, no baseline rescaling).
Raw roberta-large scores sit in roughly [0.8, 1.0] for any two English
texts, so differences are small in absolute terms.

The encoder sees at most 512 tokens, and constitutions run to 16k, so
documents are never fed whole. Instead:

1. The constitution is cut into segments (sections or subsections, see
   Constitution.from_markdown); each segment is encoded on its own, so a
   token's context is its own segment.
2. A segment longer than the encoder window is encoded in overlapping
   windows, and each token takes its embedding from the window where it
   sits farthest from an edge. Nothing is truncated.

From these token embeddings three scores are reported (BERTScoreResult):

- `document`: the formula above over all tokens of both documents. This
  is BERTScore applied to the full texts; it differs from the reference
  implementation only in that contexts are segments instead of the
  whole (unencodable) document.
- `segments_equal` / `segments_length`: per-segment-pair BERTScore F1,
  aggregated by best-match alignment (metrics/alignment.py) with equal
  or token-length weights. This is a custom aggregation, not standard
  BERTScore, and should be labeled as such.

Neither is length-insensitive by construction: dropping text from B
lowers R (fewer of A's tokens find a good match) while P can stay high.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

import numpy as np

from convergence.constitutions import Constitution
from convergence.metrics.alignment import AlignmentResult, best_match_alignment, harmonic_mean


class TokenEmbedder(Protocol):
    """Maps each text to an (n_tokens, dim) array of contextual token embeddings."""

    model_id: str

    def embed_tokens(self, texts: Sequence[str]) -> list[np.ndarray]:
        ...


def window_starts(n_tokens: int, window: int, stride: int) -> list[int]:
    """Start offsets of overlapping windows covering n_tokens tokens."""
    if n_tokens <= window:
        return [0]
    starts = list(range(0, n_tokens - window + 1, stride))
    if starts[-1] != n_tokens - window:
        starts.append(n_tokens - window)
    return starts


def assign_windows(n_tokens: int, window: int, starts: Sequence[int]) -> np.ndarray:
    """For each token, the index of the window whose centre is nearest to it.

    Only windows that contain the token are eligible, so a token always
    takes its embedding from a window that actually saw it.
    """
    pos = np.arange(n_tokens)[:, None]
    s = np.asarray(starts)[None, :]
    contains = (pos >= s) & (pos < s + window)
    dist = np.where(contains, np.abs(pos - (s + (window - 1) / 2)), np.inf)
    return dist.argmin(axis=1)


class HFTokenEmbedder:
    """Contextual token embeddings from a Hugging Face encoder (BERTScore's backbone).

    `num_layers` picks the hidden layer (hidden_states[num_layers], i.e.
    the output of the num_layers-th transformer layer), as bert_score's
    `num_layers` does; 17 is its recommended layer for roberta-large.
    Special tokens are dropped. Texts longer than `window` tokens are
    encoded in windows overlapping by `window - stride` tokens.

    If `cache_dir` is given, each text's embeddings are stored there as
    float16 .npy files keyed by (model_id, text), so re-running an
    experiment does not re-encode the constitutions. Requires `torch`
    and `transformers`.
    """

    def __init__(
        self,
        model_type: str = "roberta-large",
        num_layers: int = 17,
        window: int = 510,
        stride: int = 255,
        batch_size: int = 8,
        device: str | None = None,
        cache_dir: str | Path | None = None,
    ):
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer, GPT2Tokenizer
        except ImportError as e:
            raise ImportError(
                "HFTokenEmbedder requires 'torch' and 'transformers'. "
                'Install them with: pip install -e ".[bertscore]"'
            ) from e

        self._torch = torch
        # bert_score's defaults: slow tokenizer; byte-level BPE (RoBERTa, GPT-2)
        # with a prefix space so the first word is tokenized like the others.
        self._tokenizer = AutoTokenizer.from_pretrained(model_type, use_fast=False)
        self._encode_kwargs = (
            {"add_prefix_space": True} if isinstance(self._tokenizer, GPT2Tokenizer) else {}
        )
        self._model = AutoModel.from_pretrained(model_type)
        self._model.eval()
        self._device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model.to(self._device)
        n_hidden = self._model.config.num_hidden_layers
        if not 1 <= num_layers <= n_hidden:
            raise ValueError(f"num_layers must be in 1..{n_hidden} for {model_type}")
        self._num_layers = num_layers
        self._window = window
        self._stride = stride
        self._batch_size = batch_size
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None
        if self._cache_dir is not None:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        self.model_id = f"hf:{model_type}:L{num_layers}:w{window}:s{stride}"

    def tokenize(self, text: str) -> list[int]:
        return self._tokenizer.encode(
            text.strip(), add_special_tokens=False, **self._encode_kwargs
        )

    def _cache_path(self, text: str) -> Path | None:
        if self._cache_dir is None:
            return None
        h = hashlib.sha256(f"{self.model_id}\0{text}".encode("utf-8")).hexdigest()
        return self._cache_dir / f"{h}.npy"

    def _encode_windows(self, windows: list[list[int]]) -> list[np.ndarray]:
        torch = self._torch
        out: list[np.ndarray] = []
        cls_id, sep_id = self._tokenizer.cls_token_id, self._tokenizer.sep_token_id
        pad_id = self._tokenizer.pad_token_id
        for k in range(0, len(windows), self._batch_size):
            batch = [[cls_id, *w, sep_id] for w in windows[k : k + self._batch_size]]
            width = max(len(b) for b in batch)
            ids = torch.tensor([b + [pad_id] * (width - len(b)) for b in batch], device=self._device)
            mask = torch.tensor(
                [[1] * len(b) + [0] * (width - len(b)) for b in batch], device=self._device
            )
            with torch.no_grad():
                hidden = self._model(
                    input_ids=ids, attention_mask=mask, output_hidden_states=True
                ).hidden_states[self._num_layers]
            for row, b in zip(hidden, batch):
                out.append(row[1 : len(b) - 1].float().cpu().numpy())
        return out

    def _embed_one(self, text: str) -> np.ndarray:
        ids = self.tokenize(text)
        if not ids:
            return np.zeros((0, self._model.config.hidden_size), dtype=np.float32)
        starts = window_starts(len(ids), self._window, self._stride)
        encoded = self._encode_windows([ids[s : s + self._window] for s in starts])
        owner = assign_windows(len(ids), self._window, starts)
        return np.stack([encoded[w][i - starts[w]] for i, w in enumerate(owner)])

    def embed_tokens(self, texts: Sequence[str]) -> list[np.ndarray]:
        result = []
        for text in texts:
            path = self._cache_path(text)
            if path is not None and path.exists():
                result.append(np.load(path).astype(np.float32))
                continue
            emb = self._embed_one(text)
            if path is not None:
                np.save(path, emb.astype(np.float16))
            result.append(emb)
        return result


def _unit_rows(x: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    return x / np.where(norms == 0, 1.0, norms)


@dataclass(frozen=True)
class PRF:
    precision: float
    recall: float
    f1: float


def bertscore_from_embeddings(ref: np.ndarray, cand: np.ndarray) -> PRF:
    """BERTScore P, R, F1 of candidate token embeddings against reference ones."""
    if len(ref) == 0 or len(cand) == 0:
        return PRF(0.0, 0.0, 0.0)
    sim = _unit_rows(np.asarray(ref, np.float64)) @ _unit_rows(np.asarray(cand, np.float64)).T
    r = float(sim.max(axis=1).mean())
    p = float(sim.max(axis=0).mean())
    return PRF(p, r, harmonic_mean(p, r))


@dataclass(frozen=True)
class BERTScoreResult:
    """BERTScore of constitution B (candidate) against A (reference).

    document: standard greedy matching over all tokens of both documents.
    segments_equal / segments_length: segment-level best-match alignment
        of per-pair F1 (custom aggregation; see module docstring).
    segment_f1: the (len(A), len(B)) matrix of per-segment-pair F1.
    """

    model_id: str
    document: PRF
    segments_equal: AlignmentResult
    segments_length: AlignmentResult
    segment_f1: np.ndarray
    tokens_a: tuple[int, ...]
    tokens_b: tuple[int, ...]


def segment_scores(
    emb_a: Sequence[np.ndarray], emb_b: Sequence[np.ndarray]
) -> tuple[PRF, np.ndarray, np.ndarray, np.ndarray]:
    """Document-level PRF plus per-segment-pair P, R, F1 matrices.

    Computes the token similarity matrix one A-segment at a time (never
    the full |A| x |B| token matrix at once), reading per-segment maxima
    off it with np.maximum.reduceat.
    """
    lens_b = np.array([len(e) for e in emb_b])
    if any(len(e) == 0 for e in emb_a) or np.any(lens_b == 0):
        raise ValueError("every segment needs at least one token")
    b_all = _unit_rows(np.concatenate(emb_b).astype(np.float64))
    offsets_b = np.concatenate([[0], np.cumsum(lens_b)[:-1]])

    n_a, n_b = len(emb_a), len(emb_b)
    rec = np.zeros((n_a, n_b))
    prec = np.zeros((n_a, n_b))
    doc_row_max = []
    doc_col_max = np.full(len(b_all), -np.inf)
    for i, e in enumerate(emb_a):
        sim = _unit_rows(e.astype(np.float64)) @ b_all.T  # (len a_i, |B| tokens)
        # recall of a_i within each b_j: mean over a_i's tokens of the max over b_j's tokens
        rec[i] = np.maximum.reduceat(sim, offsets_b, axis=1).mean(axis=0)
        # precision: mean over b_j's tokens of the max over a_i's tokens
        col_max = sim.max(axis=0)
        prec[i] = np.add.reduceat(col_max, offsets_b) / lens_b
        doc_row_max.append(sim.max(axis=1))
        np.maximum(doc_col_max, col_max, out=doc_col_max)

    f1 = np.where(prec + rec > 0, 2 * prec * rec / np.where(prec + rec > 0, prec + rec, 1), 0.0)
    r = float(np.concatenate(doc_row_max).mean())
    p = float(doc_col_max.mean())
    return PRF(p, r, harmonic_mean(p, r)), prec, rec, f1


class BERTScoreMetric:
    """Compares two Constitutions with BERTScore (see module docstring).

    A Constitution's criteria are its segments, so build it with
    Constitution.from_markdown(text, level=2 or 3) for a long document.
    Each distinct segment is embedded once per metric instance.
    """

    def __init__(self, embedder: TokenEmbedder):
        self._embedder = embedder
        self._memo: dict[str, np.ndarray] = {}
        self.model_id = embedder.model_id

    def _embed(self, texts: Sequence[str]) -> list[np.ndarray]:
        missing = [t for t in dict.fromkeys(texts) if t not in self._memo]
        if missing:
            for t, e in zip(missing, self._embedder.embed_tokens(missing)):
                self._memo[t] = np.asarray(e, dtype=np.float32)
        return [self._memo[t] for t in texts]

    def __call__(self, a: Constitution, b: Constitution) -> BERTScoreResult:
        emb_a, emb_b = self._embed(list(a)), self._embed(list(b))
        document, _, _, f1 = segment_scores(emb_a, emb_b)
        tok_a = tuple(len(e) for e in emb_a)
        tok_b = tuple(len(e) for e in emb_b)
        return BERTScoreResult(
            model_id=self.model_id,
            document=document,
            segments_equal=best_match_alignment(f1),
            segments_length=best_match_alignment(f1, tok_a, tok_b),
            segment_f1=f1,
            tokens_a=tok_a,
            tokens_b=tok_b,
        )


def compare_constitutions_bertscore(
    a: Constitution,
    b: Constitution,
    model_type: str = "roberta-large",
    num_layers: int = 17,
    cache_dir: str | Path | None = ".bertscore_cache",
) -> BERTScoreResult:
    """One-call convenience wrapper: BERTScoreMetric with an HFTokenEmbedder."""
    embedder = HFTokenEmbedder(model_type=model_type, num_layers=num_layers, cache_dir=cache_dir)
    return BERTScoreMetric(embedder)(a, b)
