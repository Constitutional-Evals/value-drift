"""Pluggable text embedding backends, e : strings -> R^n.

Metric 1 (cosine similarity) depends on a fixed choice of embedding
function e. This module keeps that choice swappable and explicit, since
Lionel's notes flag "depends on the choice of e" as the metric's main
weakness.

Two API-based backends are provided out of the box:
  - OpenAIEmbedder (requires OPENAI_API_KEY; also used for OpenRouter,
    see below, since OpenRouter's embeddings endpoint is OpenAI-compatible)
  - VoyageEmbedder  (requires VOYAGE_API_KEY; Anthropic's recommended
    third-party embedding provider)

OpenRouter (https://openrouter.ai) exposes an OpenAI-compatible
embeddings endpoint at https://openrouter.ai/api/v1, so it does not need
its own client class: OpenAIEmbedder(base_url=...) points the `openai`
SDK at OpenRouter instead of api.openai.com. get_default_embedder()
wires this up automatically when CONVERGENCE_EMBEDDING_PROVIDER=openrouter.
Model names on OpenRouter are namespaced by provider, e.g.
"openai/text-embedding-3-small" or "qwen/qwen3-embedding-8b" -- see
https://openrouter.ai/docs/api_reference/embeddings for the current list.

Both are lazy-imported so that neither `openai` nor `voyageai` needs to
be installed unless that backend is actually used. A CachedEmbedder
wrapper avoids paying for (or re-issuing) the same embedding call twice,
since embeddings are deterministic for a fixed (provider, model, text).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Protocol, Sequence


class Embedder(Protocol):
    """e : strings -> R^n, applied to a batch of strings at once."""

    model_id: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding vector per input string, same order."""
        ...


class OpenAIEmbedder:
    """Embeds text with an OpenAI-compatible embeddings endpoint.

    Requires the `openai` package. Works against api.openai.com by
    default; pass base_url= (and an appropriately-namespaced model, and
    that provider's API key) to point it at any other OpenAI-compatible
    endpoint, such as OpenRouter -- see OpenRouterEmbedder below, which
    is exactly this class pre-configured for OpenRouter.
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
        base_url: str | None = None,
        provider_label: str = "openai",
    ):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(
                "OpenAIEmbedder requires the 'openai' package. "
                "Install it with: pip install openai"
            ) from e

        env_var = "OPENAI_API_KEY" if base_url is None else f"{provider_label.upper()}_API_KEY"
        key = api_key or os.environ.get(env_var)
        if not key:
            raise RuntimeError(
                f"No API key found. Set the {env_var} environment variable, "
                "or pass api_key= explicitly."
            )
        self._client = OpenAI(api_key=key, base_url=base_url)
        self.model_id = f"{provider_label}:{model}"
        self._model = model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self._model, input=list(texts))
        # The API does not guarantee order, but does return an `index`
        # field per item; sort defensively rather than trust input order.
        by_index = sorted(response.data, key=lambda d: d.index)
        return [d.embedding for d in by_index]


def OpenRouterEmbedder(
    model: str = "openai/text-embedding-3-small", api_key: str | None = None
) -> OpenAIEmbedder:
    """OpenAIEmbedder pre-configured for OpenRouter (https://openrouter.ai).

    OpenRouter's embeddings endpoint (https://openrouter.ai/api/v1/embeddings)
    is OpenAI-compatible, so this just points the `openai` SDK's base_url
    there. Requires an OPENROUTER_API_KEY. Model names are namespaced by
    underlying provider, e.g. "openai/text-embedding-3-small",
    "qwen/qwen3-embedding-8b", "voyageai/voyage-4" -- see
    https://openrouter.ai/docs/api_reference/embeddings for the current list.
    """
    return OpenAIEmbedder(
        model=model,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        provider_label="openrouter",
    )


class LocalEmbedder:
    """Embeds text with a local sentence-transformers model.

    No API key or network access needed at call time (the model weights
    are downloaded once from Hugging Face on first construction, then
    cached locally). Useful when API providers are unreachable -- e.g. a
    sandboxed environment whose egress policy blocks OpenAI/Voyage/
    OpenRouter -- or when you simply don't want per-call cost.

    Requires the `sentence-transformers` package.
    """

    def __init__(self, model: str = "sentence-transformers/all-mpnet-base-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "LocalEmbedder requires the 'sentence-transformers' package. "
                "Install it with: pip install sentence-transformers"
            ) from e

        self._model_obj = SentenceTransformer(model)
        self.model_id = f"local:{model}"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model_obj.encode(list(texts), normalize_embeddings=False)
        return [v.tolist() for v in vectors]


class VoyageEmbedder:
    """Embeds text with a Voyage AI embedding model.

    Requires the `voyageai` package and a VOYAGE_API_KEY (passed
    explicitly or read from the environment).
    """

    def __init__(self, model: str = "voyage-3", api_key: str | None = None):
        try:
            import voyageai
        except ImportError as e:
            raise ImportError(
                "VoyageEmbedder requires the 'voyageai' package. "
                "Install it with: pip install voyageai"
            ) from e

        key = api_key or os.environ.get("VOYAGE_API_KEY")
        if not key:
            raise RuntimeError(
                "No Voyage API key found. Set the VOYAGE_API_KEY environment "
                "variable, or pass api_key= explicitly."
            )
        self._client = voyageai.Client(api_key=key)
        self.model_id = f"voyage:{model}"
        self._model = model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        result = self._client.embed(list(texts), model=self._model)
        return result.embeddings


class CachedEmbedder:
    """Wraps an Embedder with a persistent on-disk cache.

    Keyed on (embedder.model_id, text), so switching models or providers
    never returns a stale cached vector. Cache is a flat JSON file of
    {sha256(model_id + text): vector}; fine for the scale of a research
    project (hundreds to low thousands of constitutions), not intended
    as a production embedding store.
    """

    def __init__(self, inner: Embedder, cache_path: str | Path = ".embedding_cache.json"):
        self._inner = inner
        self.model_id = inner.model_id
        self._cache_path = Path(cache_path)
        self._cache: dict[str, list[float]] = {}
        if self._cache_path.exists():
            self._cache = json.loads(self._cache_path.read_text())

    def _key(self, text: str) -> str:
        h = hashlib.sha256()
        h.update(self.model_id.encode("utf-8"))
        h.update(b"\0")
        h.update(text.encode("utf-8"))
        return h.hexdigest()

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        texts = list(texts)
        keys = [self._key(t) for t in texts]
        missing = [(i, t) for i, (t, k) in enumerate(zip(texts, keys)) if k not in self._cache]

        if missing:
            fresh = self._inner.embed([t for _, t in missing])
            for (i, _), vec in zip(missing, fresh):
                self._cache[keys[i]] = vec
            self._flush()

        return [self._cache[k] for k in keys]

    def _flush(self) -> None:
        self._cache_path.write_text(json.dumps(self._cache))

    @property
    def calls_avoided(self) -> int:
        """Number of distinct texts currently cached (for diagnostics)."""
        return len(self._cache)


def get_default_embedder(
    cache_path: str | Path | None = ".embedding_cache.json",
) -> Embedder:
    """Construct an embedder from environment configuration.

    Reads:
      CONVERGENCE_EMBEDDING_PROVIDER:
          "openrouter" (default), "openai", "voyage", or "local"
      CONVERGENCE_EMBEDDING_MODEL:
          provider-specific model name (optional)

    This project defaults to OpenRouter because the experiments use
    OPENROUTER_API_KEY.
    """
    provider = os.environ.get(
        "CONVERGENCE_EMBEDDING_PROVIDER", "openrouter"
    ).lower()

    model_env = os.environ.get("CONVERGENCE_EMBEDDING_MODEL")

    if provider == "openrouter":
        embedder: Embedder = OpenRouterEmbedder(
            model=model_env or "openai/text-embedding-3-small"
        )
    elif provider == "openai":
        embedder = OpenAIEmbedder(
            model=model_env or "text-embedding-3-small"
        )
    elif provider == "voyage":
        embedder = VoyageEmbedder(
            model=model_env or "voyage-3"
        )
    elif provider == "local":
        embedder = LocalEmbedder(
            model=model_env
            or "sentence-transformers/all-mpnet-base-v2"
        )
    else:
        raise ValueError(
            f"Unknown CONVERGENCE_EMBEDDING_PROVIDER={provider!r}; "
            "expected 'openrouter', 'openai', 'voyage', or 'local'."
        )

    if cache_path is None:
        return embedder

    return CachedEmbedder(
        embedder,
        cache_path=cache_path,
    )
