"""Tests for embedding backend construction/config wiring.

These only test object construction (model_id, base_url, error
messages) -- never a real network call -- so they don't need a real API
key. They're skipped automatically if the `openai` package isn't
installed, since OpenAIEmbedder/OpenRouterEmbedder require it.
"""

import os

import pytest

openai = pytest.importorskip("openai")

from convergence.embeddings import OpenAIEmbedder, OpenRouterEmbedder, get_default_embedder


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ["OPENAI_API_KEY", "OPENROUTER_API_KEY", "VOYAGE_API_KEY",
                "CONVERGENCE_EMBEDDING_PROVIDER", "CONVERGENCE_EMBEDDING_MODEL"]:
        monkeypatch.delenv(var, raising=False)


def test_openai_embedder_missing_key_raises_clear_error():
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIEmbedder()


def test_openrouter_embedder_missing_key_raises_clear_error():
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouterEmbedder()


def test_openrouter_embedder_points_at_openrouter_base_url(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-test-key")
    embedder = OpenRouterEmbedder(model="openai/text-embedding-3-small")
    assert str(embedder._client.base_url).rstrip("/") == "https://openrouter.ai/api/v1"
    assert embedder.model_id == "openrouter:openai/text-embedding-3-small"


def test_openrouter_embedder_does_not_pick_up_openai_key(monkeypatch):
    # An OPENAI_API_KEY set for the real OpenAI API should not silently
    # be reused for OpenRouter -- they're different accounts/billing.
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key-should-not-be-used")
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouterEmbedder()


def test_get_default_embedder_wires_up_openrouter_provider(monkeypatch):
    monkeypatch.setenv("CONVERGENCE_EMBEDDING_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-test-key")
    embedder = get_default_embedder(cache_path=None)
    assert embedder.model_id == "openrouter:openai/text-embedding-3-small"


def test_get_default_embedder_openrouter_respects_model_override(monkeypatch):
    monkeypatch.setenv("CONVERGENCE_EMBEDDING_PROVIDER", "openrouter")
    monkeypatch.setenv("CONVERGENCE_EMBEDDING_MODEL", "qwen/qwen3-embedding-8b")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-test-key")
    embedder = get_default_embedder(cache_path=None)
    assert embedder.model_id == "openrouter:qwen/qwen3-embedding-8b"


def test_get_default_embedder_unknown_provider_raises():
    os.environ["CONVERGENCE_EMBEDDING_PROVIDER"] = "not-a-real-provider"
    try:
        with pytest.raises(ValueError, match="openrouter"):
            get_default_embedder(cache_path=None)
    finally:
        del os.environ["CONVERGENCE_EMBEDDING_PROVIDER"]
