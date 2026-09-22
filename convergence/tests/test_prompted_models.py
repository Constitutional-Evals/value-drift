"""Tests for prompted-model construction/config wiring and error handling.

Only construction and the missing-logprobs error path are tested here --
never a real network call -- so no API key is needed. Skipped
automatically if `openai` isn't installed.
"""

import math

import pytest

openai = pytest.importorskip("openai")

from convergence.prompted_models import (
    ChatLogprobModel,
    OpenRouterChatModel,
    get_default_prompted_model,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ["OPENAI_API_KEY", "OPENROUTER_API_KEY", "CONVERGENCE_KL_PROVIDER",
                "CONVERGENCE_KL_MODEL"]:
        monkeypatch.delenv(var, raising=False)


def test_missing_key_raises_clear_error():
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        ChatLogprobModel()


def test_openrouter_missing_key_raises_clear_error():
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouterChatModel()


def test_get_default_prompted_model_defaults_to_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-test-key")
    model = get_default_prompted_model()
    assert model.model_id == "openai:gpt-4o-mini"


def test_get_default_prompted_model_openrouter(monkeypatch):
    monkeypatch.setenv("CONVERGENCE_KL_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-test-key")
    model = get_default_prompted_model()
    assert model.model_id == "openrouter:openai/gpt-4o-mini"


class _FakeChoice:
    def __init__(self, logprobs):
        self.logprobs = logprobs


class _FakeResponse:
    def __init__(self, choices):
        self.choices = choices


class _FakeCompletions:
    def __init__(self, response):
        self._response = response

    def create(self, **kwargs):
        return self._response


class _FakeChat:
    def __init__(self, response):
        self.completions = _FakeCompletions(response)


class _FakeClient:
    def __init__(self, response):
        self.chat = _FakeChat(response)


def test_raises_clear_error_when_provider_returns_no_logprobs(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-test-key")
    model = ChatLogprobModel()
    # Simulate a provider/model that ignores the logprobs request entirely.
    model._client = _FakeClient(_FakeResponse([_FakeChoice(logprobs=None)]))

    with pytest.raises(RuntimeError, match="did not return logprobs"):
        model.next_token_distribution("system prompt", "user message")


class _TopLogprob:
    def __init__(self, token, logprob):
        self.token = token
        self.logprob = logprob


class _LogprobsContent:
    def __init__(self, top_logprobs):
        self.top_logprobs = top_logprobs


class _Logprobs:
    def __init__(self, content):
        self.content = content


def test_parses_top_logprobs_into_probabilities(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-test-key")
    model = ChatLogprobModel()
    fake_top_logprobs = [
        _TopLogprob("Yes", math.log(0.7)),
        _TopLogprob("No", math.log(0.3)),
    ]
    response = _FakeResponse(
        [_FakeChoice(logprobs=_Logprobs(content=[_LogprobsContent(fake_top_logprobs)]))]
    )
    model._client = _FakeClient(response)

    dist = model.next_token_distribution("system prompt", "user message", top_k=2)
    assert dist["Yes"] == pytest.approx(0.7)
    assert dist["No"] == pytest.approx(0.3)
