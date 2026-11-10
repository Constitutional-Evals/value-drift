import math

import numpy as np
import pytest

from multi_agent_rsi.agents import ALWAYS_C, ALWAYS_D, TIT_FOR_TAT, FixedPlayer, LearnerConfig, QLearner
from multi_agent_rsi.game import C, D, Payoffs, play_round
from multi_agent_rsi.llm import parse_action, parse_rewrite
from multi_agent_rsi.utility import SocialUtility, TableUtility, TextUtility, mutate, utility_from_dict, utility_to_dict


def test_payoffs_are_a_dilemma():
    p = Payoffs()
    assert p.payoff(C, C) == (3, 3) and p.payoff(D, C) == (5, 0) and p.payoff(C, D) == (0, 5) and p.payoff(D, D) == (1, 1)
    with pytest.raises(ValueError):
        Payoffs(T=1, R=3, P=1, S=0)
    with pytest.raises(ValueError):
        Payoffs(T=10, R=3, P=1, S=0)  # 2R <= T + S


def test_fixed_players():
    r = play_round(FixedPlayer(TIT_FOR_TAT), FixedPlayer(ALWAYS_D), 10, Payoffs())
    assert r.history[0][:2] == (C, D) and all(h[:2] == (D, D) for h in r.history[1:])
    assert r.score == (0.9, 1.4)
    r = play_round(FixedPlayer(TIT_FOR_TAT), FixedPlayer(ALWAYS_C), 10, Payoffs())
    assert r.score == (3.0, 3.0) and r.coop == (1.0, 1.0)


def test_selfish_one_shot_learner_defects():
    rng = np.random.default_rng(0)
    q = QLearner(SocialUtility(), LearnerConfig(), rng)
    r = play_round(q, FixedPlayer(ALWAYS_C), 300, Payoffs())
    assert q.greedy_policy()["DC"] == D and r.late_coop[0] < 0.1


def test_cooperative_utility_learns_to_cooperate_with_tft():
    rng = np.random.default_rng(1)
    u = TableUtility(cc=10.0, cd=-5.0, dc=0.0, dd=-2.0)
    q = QLearner(u, LearnerConfig(), rng)
    r = play_round(q, FixedPlayer(TIT_FOR_TAT), 300, Payoffs())
    assert q.greedy_policy()["CC"] == C and r.late_coop[0] > 0.8


def test_utility_values():
    assert SocialUtility().value(C, D, 0, 5) == 0
    assert SocialUtility(alpha=0.5).value(C, D, 0, 5) == 2.5
    assert SocialUtility(beta=1.0).value(C, D, 0, 5) == -5
    assert SocialUtility(gamma=1.0).value(D, C, 5, 0) == 0
    assert math.isnan(TextUtility("x").value(C, C, 3, 3))


def test_mutate_and_roundtrip():
    rng = np.random.default_rng(0)
    u = SocialUtility(alpha=1.9)
    m = mutate(u, rng, sigma=5.0)
    assert -2 <= m.alpha <= 2 and m.kind == "social" and m is not u
    assert utility_from_dict(utility_to_dict(m)) == m
    with pytest.raises(TypeError):
        mutate(TextUtility("x"), rng, 0.1)


def test_parsers():
    assert parse_action("C") == C and parse_action("I choose D.") == D and parse_action("cooperate") is None
    assert parse_rewrite("KEEP") is None
    assert parse_rewrite("ok <utility> I value mutual cooperation. </utility>") == "I value mutual cooperation."
