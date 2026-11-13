"""Utility functions an agent acts on, and the mutation operator for the parametric ones.

A utility maps one game's outcome to a number the agent treats as its reward. The true
payoff matrix never changes; only the utility does.

Notation. In one game the agent plays a in {C, D}, the opponent plays b in {C, D}; the fixed
payoff matrix gives the agent pi(a, b) and the opponent pi(b, a), with pi(C,C)=R,
pi(C,D)=S, pi(D,C)=T, pi(D,D)=P and T > R > P > S, 2R > T + S.

Fitness of a utility u (what the outer loop maximises) is the mean true payoff over a round:
    F(u) = (1/N) * sum_{k=1..N} pi(a_k, b_k),   a_k chosen by a learner rewarded with u.

SocialUtility (theta = (alpha, beta, gamma); theta = 0 is pure self-interest):
    u_theta(a, b) = pi(a,b) + alpha * pi(b,a)
                    - beta  * max(pi(b,a) - pi(a,b), 0)      # dislike of being behind
                    - gamma * max(pi(a,b) - pi(b,a), 0)      # dislike of being ahead
TableUtility (theta = (u_CC, u_CD, u_DC, u_DD); theta = (R, S, T, P) is pure self-interest):
    u_theta(a, b) = theta[a b]
IndicatorUtility (theta = (coop, truth, lie, match, lied_to); theta = 0 is pure self-interest), for
games preceded by a conversation with announcements d_i in {C, D, none}:
    u_theta(a, b) = pi(a,b) + coop * 1[a = C] + truth * 1[d_i != none and a = d_i]
                    + lie * 1[d_i != none and a != d_i] + match * 1[a = b]
                    + lied_to * 1[d_j != none and b != d_j]
TextUtility: a paragraph the LLM acts on; it has no numeric form (not used in the 2x2).

Proposal step of the hill-climber, for the parametric kinds:
    mutate:  theta' = clip(theta + sigma * z, lo, hi),   z ~ N(0, I)
    llm:     theta' = clip(theta_proposed, lo, hi), theta_proposed chosen by the model, which
             is shown the formula, the code, the current theta and the last round's result.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Protocol

import numpy as np


class Utility(Protocol):
    kind: str
    def value(self, own: str, other: str, own_payoff: float, other_payoff: float) -> float: ...
    def params(self) -> dict: ...
    def describe(self) -> str: ...


@dataclass(frozen=True)
class SocialUtility:
    """u(a,b) = pi(a,b) + alpha*pi(b,a) - beta*max(pi(b,a)-pi(a,b), 0) - gamma*max(pi(a,b)-pi(b,a), 0)

    Own payoff plus a weight on the other's payoff and Fehr-Schmidt inequity terms.
    alpha = beta = gamma = 0 is pure self-interest (utility equals the true payoff).
    """
    alpha: float = 0.0   # weight on the other's payoff
    beta: float = 0.0    # dislike of being behind (other - own > 0)
    gamma: float = 0.0   # dislike of being ahead (own - other > 0)
    kind: str = "social"

    def value(self, own: str, other: str, own_payoff: float, other_payoff: float) -> float:
        return (own_payoff + self.alpha * other_payoff
                - self.beta * max(other_payoff - own_payoff, 0.0)
                - self.gamma * max(own_payoff - other_payoff, 0.0))

    def params(self) -> dict:
        return {"alpha": self.alpha, "beta": self.beta, "gamma": self.gamma}

    @staticmethod
    def template() -> str:
        """The functional form with symbolic parameters (no values)."""
        return ("u(a, b) = pi(a, b) + alpha * pi(b, a) - beta * max(pi(b, a) - pi(a, b), 0) "
                "- gamma * max(pi(a, b) - pi(b, a), 0)\n"
                "where pi(a, b) is your payoff and pi(b, a) the opponent's payoff from the payoff matrix "
                "when you play a and they play b. In code:\n"
                "def utility(own_payoff, other_payoff, alpha, beta, gamma):\n"
                "    return (own_payoff + alpha * other_payoff\n"
                "            - beta * max(other_payoff - own_payoff, 0)\n"
                "            - gamma * max(own_payoff - other_payoff, 0))")

    def formula(self) -> str:
        """Closed form with the current parameter values substituted."""
        return (f"u(a, b) = pi(a, b) + {self.alpha:.2f} * pi(b, a) "
                f"- {self.beta:.2f} * max(pi(b, a) - pi(a, b), 0) "
                f"- {self.gamma:.2f} * max(pi(a, b) - pi(b, a), 0)")

    def code(self) -> str:
        return ("def utility(own_payoff, other_payoff):\n"
                f"    alpha, beta, gamma = {self.alpha:.2f}, {self.beta:.2f}, {self.gamma:.2f}\n"
                "    return (own_payoff + alpha * other_payoff\n"
                "            - beta * max(other_payoff - own_payoff, 0)\n"
                "            - gamma * max(own_payoff - other_payoff, 0))")

    def describe(self) -> str:
        return (f"{self.formula()}\nwhere pi(a, b) is your payoff and pi(b, a) the opponent's payoff "
                f"from the payoff matrix when you play a and they play b. In code:\n{self.code()}")


@dataclass(frozen=True)
class TableUtility:
    """u(a,b) = theta[ab]: one subjective value per joint outcome (own action, other action).

    (cc, cd, dc, dd) = (R, S, T, P) is pure self-interest.
    """
    cc: float = 3.0
    cd: float = 0.0
    dc: float = 5.0
    dd: float = 1.0
    kind: str = "table"

    def value(self, own: str, other: str, own_payoff: float, other_payoff: float) -> float:
        return {"CC": self.cc, "CD": self.cd, "DC": self.dc, "DD": self.dd}[own + other]

    def params(self) -> dict:
        return {"cc": self.cc, "cd": self.cd, "dc": self.dc, "dd": self.dd}

    @staticmethod
    def template() -> str:
        return ("u(a, b) = theta[a b], one value per joint outcome: parameters cc, cd, dc, dd\n"
                "where a is your move and b the opponent's move (C or D). In code:\n"
                "def utility(own_move, other_move, cc, cd, dc, dd):\n"
                "    return {'CC': cc, 'CD': cd, 'DC': dc, 'DD': dd}[own_move + other_move]")

    def formula(self) -> str:
        return (f"u(a, b) = theta[a b] with theta[CC] = {self.cc:.2f}, theta[CD] = {self.cd:.2f}, "
                f"theta[DC] = {self.dc:.2f}, theta[DD] = {self.dd:.2f}")

    def code(self) -> str:
        return ("def utility(own_move, other_move):\n"
                f"    theta = {{'CC': {self.cc:.2f}, 'CD': {self.cd:.2f}, 'DC': {self.dc:.2f}, 'DD': {self.dd:.2f}}}\n"
                "    return theta[own_move + other_move]")

    def describe(self) -> str:
        return (f"{self.formula()}\nwhere a is your move and b the opponent's move (C or D). "
                f"In code:\n{self.code()}")


# name -> (formula label, template label, code condition); the order is the display order
INDICATOR_TERMS = {
    "coop": ("1[a = C]", "1[a = C]", "own_move == 'C'"),
    "truth": ("1[announced and kept]", "1[you announced a move and played it]",
              "own_announce != 'none' and own_move == own_announce"),
    "lie": ("1[announced and broke]", "1[you announced a move and played the other]",
            "own_announce != 'none' and own_move != own_announce"),
    "match": ("1[a = b]", "1[a = b]", "own_move == other_move"),
    "lied_to": ("1[opponent announced and broke]", "1[the opponent announced a move and played the other]",
                "other_announce != 'none' and other_move != other_announce"),
}


@dataclass(frozen=True)
class IndicatorUtility:
    """u = pi(a, b) + coop*1[a=C] + truth*1[announced and kept] + lie*1[announced and broke]
           + match*1[a=b] + lied_to*1[opponent announced and broke]

    For games preceded by a conversation in which each agent may announce its move (C, D or
    none). theta = 0 is pure self-interest. A single cooperate term suffices: a separate defect
    term would only add a constant plus a neutral direction. `terms` selects which weights the
    utility has; a config that omits a weight drops it from the formula, the code and the
    proposals (lied_to cannot affect the agent's own choice, so it is often left out).
    """
    coop: float = 0.0
    truth: float = 0.0
    lie: float = 0.0
    match: float = 0.0
    lied_to: float = 0.0
    terms: tuple = tuple(INDICATOR_TERMS)
    kind: str = "indicator"

    def value(self, own: str, other: str, own_payoff: float, other_payoff: float,
              own_announce: str = "none", other_announce: str = "none") -> float:
        fires = {"coop": own == "C",
                 "truth": own_announce != "none" and own == own_announce,
                 "lie": own_announce != "none" and own != own_announce,
                 "match": own == other,
                 "lied_to": other_announce != "none" and other != other_announce}
        return own_payoff + sum(getattr(self, t) * fires[t] for t in self.terms)

    def params(self) -> dict:
        return {t: getattr(self, t) for t in self.terms}

    def template(self) -> str:
        terms = self.terms
        return ("u = pi(a, b) + " + " + ".join(f"{t} * {INDICATOR_TERMS[t][1]}" for t in terms) + "\n"
                "where pi(a, b) is your payoff from the payoff matrix when you play a and the opponent plays b, "
                "1[.] is 1 when the event happens and 0 otherwise, and announcements are made in the "
                "conversation before the game (C, D or none). In code:\n"
                "def utility(own_move, other_move, own_payoff, own_announce, other_announce,\n"
                "            " + ", ".join(terms) + "):\n"
                "    u = own_payoff\n"
                + "".join(f"    u += {t:<7} * ({INDICATOR_TERMS[t][2]})\n" for t in terms) +
                "    return u")

    def formula(self) -> str:
        return "u = pi(a, b) + " + " + ".join(f"{getattr(self, t):.2f} * {INDICATOR_TERMS[t][0]}" for t in self.terms)

    def code(self) -> str:
        return ("def utility(own_move, other_move, own_payoff, own_announce, other_announce):\n"
                f"    {', '.join(self.terms)} = {', '.join(f'{getattr(self, t):.2f}' for t in self.terms)}\n"
                "    u = own_payoff\n"
                + "".join(f"    u += {t:<7} * ({INDICATOR_TERMS[t][2]})\n" for t in self.terms) +
                "    return u")

    def describe(self) -> str:
        return (f"{self.formula()}\nwhere pi(a, b) is your payoff from the payoff matrix when you play a and the "
                "opponent plays b, 1[.] is 1 when the event happens and 0 otherwise, and announcements are the "
                f"moves declared in the conversation before the game (C, D or none). In code:\n{self.code()}")


@dataclass(frozen=True)
class TextUtility:
    """A natural-language utility, acted on by an LLM. Has no numeric value."""
    text: str
    kind: str = "text"

    def value(self, own: str, other: str, own_payoff: float, other_payoff: float) -> float:
        return math.nan

    def params(self) -> dict:
        return {"text": self.text}

    def describe(self) -> str:
        return self.text


DEFAULT_BOUNDS = {"social": {"alpha": (-2.0, 2.0), "beta": (-2.0, 2.0), "gamma": (-2.0, 2.0)},
                  "table": {k: (-10.0, 10.0) for k in ("cc", "cd", "dc", "dd")},
                  "indicator": {k: (-5.0, 5.0) for k in ("coop", "truth", "lie", "match", "lied_to")}}


def utility_from_dict(d: dict) -> Utility:
    d = dict(d)
    kind = d.pop("kind")
    if kind == "social":
        return SocialUtility(**d)
    if kind == "table":
        return TableUtility(**d)
    if kind == "indicator":   # the weights present are the utility's terms; none listed means all of them
        terms = tuple(t for t in INDICATOR_TERMS if t in d) or tuple(INDICATOR_TERMS)
        return IndicatorUtility(**d, terms=terms)
    if kind == "text":
        return TextUtility(**d)
    raise ValueError(f"unknown utility kind {kind!r}")


def utility_to_dict(u: Utility) -> dict:
    return {"kind": u.kind, **u.params()}


def bounds_for(u: Utility, bounds: dict | None = None) -> dict:
    """{param: (lo, hi)} for a parametric utility, from the config or DEFAULT_BOUNDS."""
    if u.kind == "text":
        raise TypeError("text utilities have no parameter bounds")
    b = (bounds or {}).get(u.kind) or DEFAULT_BOUNDS[u.kind]
    return {k: tuple(b[k]) for k in u.params()}


def with_params(u: Utility, new: dict, bounds: dict | None = None) -> Utility:
    """Copy of u with the given parameter values, clipped to bounds. Unknown names are ignored."""
    b = bounds_for(u, bounds)
    vals = {k: float(np.clip(float(new[k]), *b[k])) for k in u.params() if k in new}
    return replace(u, **vals)


def mutate(u: Utility, rng: np.random.Generator, sigma: float, bounds: dict | None = None) -> Utility:
    """Gaussian perturbation of every parameter, clipped to bounds. Text utilities are
    rewritten by the LLM instead (see llm.py), never here."""
    if u.kind == "text":
        raise TypeError("text utilities are rewritten by the model, not mutated numerically")
    b = (bounds or {}).get(u.kind) or DEFAULT_BOUNDS[u.kind]
    new = {}
    for name, val in u.params().items():
        lo, hi = b[name]
        new[name] = float(np.clip(val + rng.normal(0.0, sigma), lo, hi))
    return replace(u, **new)


def distance_from_selfish(u: Utility) -> float:
    """How far the utility sits from pure self-interest, in parameter space (NaN for text)."""
    if u.kind == "social":
        return float(math.sqrt(u.alpha ** 2 + u.beta ** 2 + u.gamma ** 2))
    if u.kind == "table":
        return math.nan  # depends on the payoff matrix; computed in report.py
    if u.kind == "indicator":
        return float(math.sqrt(sum(v ** 2 for v in u.params().values())))
    return math.nan
