"""Prompted chat models: e(C, m) as a next-token probability distribution.

Metric 2 in Lionel's notes needs, for a constitution C and scenario s, the
distribution M produces when prompted with (C, s):

    K(C||C') := E_{s ~ S} [d_KL(M prompted with C,s || M prompted with C',s)]

That's a KL divergence between two *full response* distributions, which is
intractable to compute exactly (it would require summing over every
possible response string). This module implements the cheap, tractable
approximation: the KL divergence between the two *next-token*
distributions only (the model's distribution over its very first output
token, given the constitution as a system prompt and a user message).
convergence.metrics.kl also drops the E_{s ~ S} scenario expectation and
evaluates at a single fixed user message instead -- see that module's
docstring for why and for what a truer sequence-level, scenario-averaged
estimator would need.

`ChatLogprobModel` gets that next-token distribution from any
OpenAI-compatible chat completions endpoint that supports the
`logprobs` / `top_logprobs` request parameters (OpenAI directly, or
OpenRouter -- support varies by which underlying provider/model
OpenRouter routes to, since it's a passthrough parameter; OpenAI-hosted
models are the safest bet). Not all models/providers return logprobs,
so this raises a clear error rather than silently returning nonsense
when they don't.
"""

from __future__ import annotations

import math
import os
from typing import Protocol


class PromptedModel(Protocol):
    """M(system_prompt, user_message) -> next-token distribution."""

    model_id: str

    def next_token_distribution(
        self, system_prompt: str, user_message: str, top_k: int = 20
    ) -> dict[str, float]:
        """Return {token: probability} for the top_k most likely next tokens.

        This is *not* a full probability distribution over the vocabulary
        -- it's the top_k highest-probability tokens only, which is all
        most APIs expose. Callers (see metrics/kl.py) must account for
        the missing tail mass rather than assume these probabilities sum
        to 1.
        """
        ...


class ChatLogprobModel:
    """Next-token distribution via an OpenAI-compatible chat completions API.

    Works against api.openai.com by default; pass base_url= to point it
    at OpenRouter or another OpenAI-compatible provider (see
    OpenRouterChatModel below for a pre-configured constructor).

    Uses temperature=1.0, top_p=1.0 on the request so the returned
    logprobs reflect the model's own distribution as closely as the API
    allows, rather than a sampling-parameter-distorted one -- though note
    some providers still apply their own default penalties/processing
    that this can't fully undo.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
        provider_label: str = "openai",
    ):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(
                "ChatLogprobModel requires the 'openai' package. "
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

    def next_token_distribution(
        self, system_prompt: str, user_message: str, top_k: int = 20
    ) -> dict[str, float]:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=1,
            temperature=1.0,
            top_p=1.0,
            logprobs=True,
            top_logprobs=top_k,
        )
        choice = response.choices[0]
        logprobs_obj = getattr(choice, "logprobs", None)
        content = getattr(logprobs_obj, "content", None) if logprobs_obj else None
        if not content:
            raise RuntimeError(
                f"Model '{self._model}' did not return logprobs. Not every "
                "model/provider supports the logprobs/top_logprobs request "
                "parameters (support varies, especially when routed through "
                "OpenRouter) -- try an OpenAI-hosted model, or a provider "
                "you've confirmed returns them."
            )
        top_logprobs = content[0].top_logprobs
        return {entry.token: math.exp(entry.logprob) for entry in top_logprobs}


def OpenRouterChatModel(
    model: str = "openai/gpt-4o-mini", api_key: str | None = None
) -> ChatLogprobModel:
    """ChatLogprobModel pre-configured for OpenRouter (https://openrouter.ai).

    Requires OPENROUTER_API_KEY. Defaults to an OpenAI-hosted model
    routed through OpenRouter, since OpenAI's own logprobs support is
    well-established; support for non-OpenAI models varies by provider
    (OpenRouter passes the parameter through, it doesn't guarantee the
    backend honors it) -- see
    https://openrouter.ai/docs/api_reference/parameters and check the
    specific model's provider notes before relying on another one.
    """
    return ChatLogprobModel(
        model=model,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        provider_label="openrouter",
    )


def get_default_prompted_model() -> PromptedModel:
    """Construct a prompted model from environment configuration.

    Reads:
      CONVERGENCE_KL_PROVIDER:
          "openrouter" (default) or "openai"
      CONVERGENCE_KL_MODEL:
          provider-specific model name (optional)

    This project defaults to OpenRouter because the experiments use
    OPENROUTER_API_KEY.
    """
    provider = os.environ.get(
        "CONVERGENCE_KL_PROVIDER", "openrouter"
    ).lower()

    model_env = os.environ.get("CONVERGENCE_KL_MODEL")

    if provider == "openrouter":
        return OpenRouterChatModel(
            model=model_env or "openai/gpt-4o-mini"
        )

    if provider == "openai":
        return ChatLogprobModel(
            model=model_env or "gpt-4o-mini"
        )

    raise ValueError(
        f"Unknown CONVERGENCE_KL_PROVIDER={provider!r}; "
        "expected 'openrouter' or 'openai'."
    )
