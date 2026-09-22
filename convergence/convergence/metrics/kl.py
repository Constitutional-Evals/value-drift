"""Metric 2 from Lionel's notes: KL divergence between prompted models.

    K(C||C') := E_{s ~ S} [d_KL(M prompted with C,s || M prompted with C',s)]

Depends on: open-weight language model M and scenario distribution S.

Pros: behavioral.
Cons: asymmetric; depends on M and S; sensitive to style. (The M
dependence can be mitigated by averaging over a few different choices of
M -- not yet implemented here; see PromptedKLMetric's docstring.)

--- Implementation note: no scenario distribution S here ---

This implementation drops the E_{s ~ S} expectation entirely: instead of
averaging over a scenario distribution, it evaluates the next-token
distribution at one fixed, neutral user message (see
PromptedKLMetric.DEFAULT_USER_MESSAGE), the same message for both C and
C'. This is a further simplification on top of the next-token
approximation below -- it trades the "behavioral, averaged over
situations" character of the notes' K(C||C') for a single-prompt
snapshot, which is cheaper and easier to reason about but blind to
scenario-dependent divergence (two constitutions that agree at the
neutral prompt but diverge sharply on, say, a moral-weight question would
look identical here). Pass a different `user_message` to PromptedKLMetric
if the fixed default isn't the right probe.

--- Implementation note: this is the next-token approximation ---

d_KL(M(.|C,s) || M(.|C',s)) in the notes is a KL divergence between two
distributions over *entire responses*. That's intractable to compute
exactly (summing over every possible response string), and a faithful
Monte Carlo estimate needs teacher-forced logprobs for arbitrarily
supplied continuations under two different prompts -- which most hosted
chat APIs don't expose (they only return logprobs for tokens they
themselves generated), typically requiring a local open-weight model
instead.

What's implemented here instead is the KL divergence between the two
*next-token* distributions only -- i.e. just the first token of the
response. This is: (a) tractable via any provider that supports
`logprobs`/`top_logprobs` on chat completions (see
convergence.prompted_models), (b) a real, directionally meaningful
signal (constitutions that disagree strongly will often disagree
immediately about how to start responding), but (c) blind to
divergence that only shows up later in a response (e.g. two
constitutions that open the same way but diverge by the second
sentence). Treat this as a fast first-pass proxy for K(C||C'), not a
faithful implementation of the formula -- a sequence-level Monte Carlo
estimator (sample full responses, score them under both prompts) would
be a natural next step and is a distinct implementation choice, not a
bug fix to this one.

Additionally, `top_logprobs` only returns the top_k highest-probability
tokens, not the full vocabulary distribution -- the KL computation below
assigns a small `epsilon` floor to any token seen in one distribution's
top_k but not the other's, then renormalizes each distribution over the
union of observed tokens. This is a standard way to make the estimator
well-defined despite the truncation, but it undercounts genuine
tail-probability mass the API never reports, so treat KL values as
approximate and biased toward zero.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from convergence.constitutions import Constitution
from convergence.prompted_models import PromptedModel


def next_token_kl_divergence(
    p: dict[str, float], q: dict[str, float], epsilon: float = 1e-8
) -> float:
    """KL(P || Q) over the union of two top-k token distributions.

    p, q: {token: probability} from PromptedModel.next_token_distribution,
    generally *not* summing to 1 (they're truncated to the top_k tokens).
    Tokens present in one distribution but absent from the other are
    assigned `epsilon` before renormalization, so KL stays finite;
    without this, a token with p(x) > 0 but q(x) = 0 would make KL(P||Q)
    diverge to infinity, which would say more about API truncation than
    about the constitutions.
    """
    support = set(p) | set(q)
    if not support:
        return 0.0

    p_full = {t: p.get(t, epsilon) for t in support}
    q_full = {t: q.get(t, epsilon) for t in support}

    p_sum = sum(p_full.values())
    q_sum = sum(q_full.values())
    p_norm = {t: v / p_sum for t, v in p_full.items()}
    q_norm = {t: v / q_sum for t, v in q_full.items()}

    return float(sum(pt * math.log(pt / q_norm[t]) for t, pt in p_norm.items() if pt > 0))


class PromptedKLMetric:
    """Computes K(C, C') = KL(M(.|C) || M(.|C')) at a single fixed prompt
    (next-token approximation, no scenario distribution -- see the module
    docstring for why).

    Asymmetric by construction, matching Lionel's notes: __call__(c1, c2)
    computes K(c1 || c2), i.e. "how much does the model prompted with c1
    diverge from the model prompted with c2" -- swap the arguments for
    the other direction. Use `symmetrized()` for a cheap, order-independent
    summary when you want a single number rather than a directed one.

    The M dependence the notes flag can be mitigated by averaging over a
    few different choices of M; that's not automated here yet -- run this
    metric once per model and average the results yourself in the
    meantime.
    """

    DEFAULT_USER_MESSAGE = "How should you respond?"

    def __init__(
        self,
        model: PromptedModel,
        user_message: str = DEFAULT_USER_MESSAGE,
        top_k: int = 20,
        epsilon: float = 1e-8,
    ):
        self._model = model
        self._user_message = user_message
        self._top_k = top_k
        self._epsilon = epsilon

    def __call__(self, c1: Constitution, c2: Constitution) -> float:
        p = self._model.next_token_distribution(c1.to_text(), self._user_message, top_k=self._top_k)
        q = self._model.next_token_distribution(c2.to_text(), self._user_message, top_k=self._top_k)
        return next_token_kl_divergence(p, q, self._epsilon)

    def symmetrized(self, c1: Constitution, c2: Constitution) -> float:
        """0.5 * (K(c1||c2) + K(c2||c1)).

        Not the formula in the notes (which is explicitly asymmetric),
        but a convenient order-independent summary when you want one
        number rather than a directed pair.
        """
        return 0.5 * (self(c1, c2) + self(c2, c1))
