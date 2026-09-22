"""A deterministic, offline stand-in for a real PromptedModel, for tests."""

from __future__ import annotations

import hashlib


class FakePromptedModel:
    """Maps (system_prompt, user_message) to a deterministic top-k distribution.

    Two different system_prompt values with the same user_message get
    genuinely different distributions (derived from a hash of both
    strings together), so tests can assert KL > 0 for different
    constitutions and KL == 0 for identical ones.
    """

    def __init__(self, model_id: str = "fake:next-token-v1", vocab_size: int = 12):
        self.model_id = model_id
        self._vocab_size = vocab_size
        self.call_count = 0

    def next_token_distribution(
        self, system_prompt: str, user_message: str, top_k: int = 20
    ) -> dict[str, float]:
        self.call_count += 1
        k = min(top_k, self._vocab_size)
        # Deterministic pseudo-logits from a hash of (system_prompt, user_message, token index).
        raw = []
        for i in range(self._vocab_size):
            h = hashlib.sha256(f"{system_prompt}\0{user_message}\0{i}".encode()).digest()
            raw.append(int.from_bytes(h[:4], "big") / 2**32)  # in [0, 1)

        # Softmax-like normalization over the full (fake) vocab, then keep top_k.
        total = sum(raw)
        probs = [r / total for r in raw]
        ranked = sorted(range(self._vocab_size), key=lambda i: -probs[i])[:k]
        return {f"tok_{i}": probs[i] for i in ranked}
