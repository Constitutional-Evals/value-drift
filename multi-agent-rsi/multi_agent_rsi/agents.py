"""Players: a tabular Q-learner rewarded by its utility, and an LLM prompted with its utility.

The inner loop (how a player chooses actions given a utility) is what makes the utility
matter. Without it, the utility is a label and hill-climbing it measures nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .game import ACTIONS, C, D, Hist
from .utility import Utility


@dataclass
class LearnerConfig:
    lr: float = 0.5                # tabular, near-deterministic rewards: a high rate is fine
    discount: float = 0.5          # enough to learn reciprocity against tit-for-tat; at 0.9 the
                                   # continuation value swamps action differences in a 300-game life
    epsilon: float = 0.3
    epsilon_decay: float = 0.98    # per game within a round
    epsilon_min: float = 0.02
    warm_start: bool = False       # keep Q across rounds (within one evaluation call only)
    optimistic_init: float = 5.0   # initial Q value; optimism makes both actions get tried


class QLearner:
    """Memory-one Q-learning. State = last joint outcome ('start', 'CC', 'CD', 'DC', 'DD');
    reward = utility of the game's outcome. Q is reset at the start of each round unless
    warm_start is set, so a round is the learner's whole lifetime."""

    STATES = ("start", "CC", "CD", "DC", "DD")

    def __init__(self, utility: Utility, cfg: LearnerConfig, rng: np.random.Generator):
        self.utility = utility
        self.cfg = cfg
        self.rng = rng
        self.q = {s: {a: cfg.optimistic_init for a in ACTIONS} for s in self.STATES}
        self.state = "start"
        self.eps = cfg.epsilon

    def begin_round(self) -> None:
        if not self.cfg.warm_start:
            self.q = {s: {a: self.cfg.optimistic_init for a in ACTIONS} for s in self.STATES}
        self.state = "start"
        self.eps = self.cfg.epsilon

    def act(self, history: Hist) -> str:
        if self.rng.random() < self.eps:
            return str(self.rng.choice(ACTIONS))
        qs = self.q[self.state]
        if qs[C] == qs[D]:
            return str(self.rng.choice(ACTIONS))
        return C if qs[C] > qs[D] else D

    def observe(self, own: str, other: str, own_payoff: float, other_payoff: float) -> None:
        r = self.utility.value(own, other, own_payoff, other_payoff)
        s2 = own + other
        target = r + self.cfg.discount * max(self.q[s2].values())
        self.q[self.state][own] += self.cfg.lr * (target - self.q[self.state][own])
        self.state = s2
        self.eps = max(self.cfg.epsilon_min, self.eps * self.cfg.epsilon_decay)

    def greedy_policy(self) -> dict[str, str]:
        return {s: (C if self.q[s][C] > self.q[s][D] else D) for s in self.STATES}


@dataclass
class FixedPlayer:
    """Deterministic memory-one strategy, for tests and baselines. policy maps state -> action."""
    policy: dict[str, str]
    state: str = "start"

    def begin_round(self) -> None:
        self.state = "start"

    def act(self, history: Hist) -> str:
        return self.policy[self.state]

    def observe(self, own: str, other: str, own_payoff: float, other_payoff: float) -> None:
        self.state = own + other


TIT_FOR_TAT = {"start": C, "CC": C, "CD": D, "DC": C, "DD": D}
ALWAYS_D = {s: D for s in QLearner.STATES}
ALWAYS_C = {s: C for s in QLearner.STATES}


class LLMPlayer:
    """Chooses C or D by asking a chat model, with its utility (formula and code) and recent
    history in the prompt. With llm.show_opponent_utility the opponent's current utility is in
    the prompt as well; otherwise the model never sees it."""

    def __init__(self, utility: Utility, chat, payoffs, n_games: int, history_window: int = 10,
                 name: str = "agent", opponent_utility: Utility | None = None, tell_horizon: bool = True,
                 talk: bool = False, history_payoffs: bool = True):
        from . import llm
        self.utility = utility
        self.opponent_text = opponent_utility.describe() if opponent_utility is not None else None
        self.chat = chat
        self.payoffs = payoffs
        self.n_games = n_games
        self.window = history_window
        self.name = name
        self.tell_horizon = tell_horizon
        self.history_payoffs = history_payoffs
        self.talk = talk                     # a conversation precedes each game (set via say()/set_conversation)
        self.conversation: list[dict] | None = [] if talk else None
        self._llm = llm
        self.raw: list[str] = []
        self.unparsed = 0

    def begin_round(self) -> None:
        self.raw = []
        self.unparsed = 0

    def say(self, transcript: list[dict], messages_each: int, announce: bool = False) -> dict:
        """One conversation message, given the transcript so far: {"text", "announce"}. With
        announce=True the reply must carry an announce tag; a missing tag counts as "none"."""
        user = self._llm.talk_prompt(self.utility.describe(), self.payoffs, transcript, self.name,
                                     self.opponent_text, messages_each, announce)
        text, _ = self.chat.complete_full(self._llm.TALK_SYSTEM, user)
        if not announce:
            return {"text": text.strip(), "announce": None}
        tag = self._llm.parse_announce(text)
        return {"text": self._llm.strip_announce(text), "announce": tag if tag is not None else "none",
                "announce_missing": tag is None}

    def set_conversation(self, transcript: list[dict]) -> None:
        self.conversation = list(transcript)

    def act(self, history: Hist) -> str:
        user = self._llm.action_prompt(self.utility.describe(), self.payoffs, history, self.n_games, self.window,
                                       self.opponent_text, self.tell_horizon, self.conversation, self.name,
                                       self.history_payoffs)
        text, finish = self.chat.complete_full(self._llm.ACTION_SYSTEM, user)
        action = self._llm.parse_action(text)
        retried = False
        if action is None and finish == "length":
            # cut off before the move tag: ask once more with three times the budget
            retried = True
            text, finish = self.chat.complete_full(self._llm.ACTION_SYSTEM, user, max_tokens=3 * self.chat.max_tokens)
            action = self._llm.parse_action(text)
        self.raw.append({"game": len(history) + 1, "reply": text, "parsed": action, "finish": finish,
                         "retried": retried})
        if action is None:
            self.unparsed += 1
            action = D  # an unreadable answer is scored as defection and counted
        return action

    def observe(self, own: str, other: str, own_payoff: float, other_payoff: float) -> None:
        pass
