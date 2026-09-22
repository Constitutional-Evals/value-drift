"""A deterministic, offline stand-in for a real Embedder, for tests.

Maps each text to a bag-of-words hashing vector: no network calls, no
API key, fully reproducible. Similar texts (sharing many words) get
higher cosine similarity than dissimilar texts, which is enough to
exercise the metric's logic without depending on a real embedding
model.
"""

from __future__ import annotations

import hashlib
from typing import Sequence

DIM = 64


class FakeEmbedder:
    def __init__(self, model_id: str = "fake:bow-hash-v1"):
        self.model_id = model_id
        self.call_count = 0
        self.texts_seen: list[str] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.call_count += 1
        self.texts_seen.extend(texts)
        return [self._embed_one(t) for t in texts]

    @staticmethod
    def _embed_one(text: str) -> list[float]:
        vec = [0.0] * DIM
        for word in text.lower().split():
            h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
            vec[h % DIM] += 1.0
        return vec
