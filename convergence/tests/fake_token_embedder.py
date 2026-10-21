"""A deterministic, offline stand-in for a contextual token embedder, for tests.

Each whitespace token maps to a fixed pseudo-random vector seeded by the
word, so the same word always gets the same embedding (no context): no
network, no model download, fully reproducible. Enough to exercise
BERTScore's matching and aggregation logic, not to judge its quality.
"""

from __future__ import annotations

import hashlib
from typing import Sequence

import numpy as np

DIM = 32


class FakeTokenEmbedder:
    def __init__(self, model_id: str = "fake:word-hash-tokens-v1"):
        self.model_id = model_id
        self.texts_seen: list[str] = []

    def embed_tokens(self, texts: Sequence[str]) -> list[np.ndarray]:
        self.texts_seen.extend(texts)
        return [self._embed_one(t) for t in texts]

    @staticmethod
    def _embed_one(text: str) -> np.ndarray:
        rows = []
        for word in text.lower().split():
            seed = int(hashlib.sha256(word.encode("utf-8")).hexdigest()[:8], 16)
            rows.append(np.random.default_rng(seed).standard_normal(DIM))
        return np.array(rows, dtype=np.float32).reshape(-1, DIM)
