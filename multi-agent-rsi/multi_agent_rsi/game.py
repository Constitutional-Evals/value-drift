"""Prisoner's dilemma stage game and one round of N games between two players."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

C, D = "C", "D"
ACTIONS = (C, D)
Hist = list[tuple[str, str, float, float]]  # (own action, other action, own payoff, other payoff)


@dataclass(frozen=True)
class Payoffs:
    T: float = 5.0
    R: float = 3.0
    P: float = 1.0
    S: float = 0.0

    def __post_init__(self) -> None:
        if not (self.T > self.R > self.P > self.S):
            raise ValueError("prisoner's dilemma needs T > R > P > S")
        if not (2 * self.R > self.T + self.S):
            raise ValueError("prisoner's dilemma needs 2R > T + S")

    def payoff(self, own: str, other: str) -> tuple[float, float]:
        if own == C and other == C:
            return self.R, self.R
        if own == C and other == D:
            return self.S, self.T
        if own == D and other == C:
            return self.T, self.S
        return self.P, self.P

    def table(self) -> dict[str, tuple[float, float]]:
        return {"CC": (self.R, self.R), "CD": (self.S, self.T), "DC": (self.T, self.S), "DD": (self.P, self.P)}

    def describe(self) -> str:
        return (f"Both cooperate: {self.R:g} each. Both defect: {self.P:g} each. "
                f"You defect while the other cooperates: you {self.T:g}, they {self.S:g}. "
                f"You cooperate while the other defects: you {self.S:g}, they {self.T:g}.")


class Player(Protocol):
    def begin_round(self) -> None: ...
    def act(self, history: Hist) -> str: ...
    def observe(self, own: str, other: str, own_payoff: float, other_payoff: float) -> None: ...


@dataclass
class RoundResult:
    history: Hist                    # from player A's view
    score: tuple[float, float]       # mean true payoff, A and B
    coop: tuple[float, float]        # cooperation rate over the round
    late_coop: tuple[float, float]   # cooperation rate over the last quarter

    def to_dict(self) -> dict:
        return {"score": list(self.score), "coop": list(self.coop), "late_coop": list(self.late_coop),
                "n_games": len(self.history)}


def play_round(a: Player, b: Player, n_games: int, payoffs: Payoffs, concurrent: bool = False,
               before_game=None) -> RoundResult:
    """Moves are simultaneous, so with concurrent=True the two act() calls run in parallel
    threads (for players that block on network calls; never for players sharing an RNG).
    before_game(game_index) runs before each game's moves (e.g. a conversation between the players)."""
    if n_games < 1:
        raise ValueError("n_games must be at least 1")
    a.begin_round(); b.begin_round()
    hist_a: Hist = []
    hist_b: Hist = []
    pool = ThreadPoolExecutor(max_workers=2) if concurrent else None
    for g in range(n_games):
        if before_game is not None:
            before_game(g)
        if pool is not None:
            fa, fb = pool.submit(a.act, hist_a), pool.submit(b.act, hist_b)
            act_a, act_b = fa.result(), fb.result()
        else:
            act_a = a.act(hist_a)
            act_b = b.act(hist_b)
        pay_a, pay_b = payoffs.payoff(act_a, act_b)
        a.observe(act_a, act_b, pay_a, pay_b)
        b.observe(act_b, act_a, pay_b, pay_a)
        hist_a.append((act_a, act_b, pay_a, pay_b))
        hist_b.append((act_b, act_a, pay_b, pay_a))
    n = len(hist_a)
    tail = max(1, n // 4)
    score = (sum(h[2] for h in hist_a) / n, sum(h[3] for h in hist_a) / n)
    coop = (sum(h[0] == C for h in hist_a) / n, sum(h[1] == C for h in hist_a) / n)
    late = (sum(h[0] == C for h in hist_a[-tail:]) / tail, sum(h[1] == C for h in hist_a[-tail:]) / tail)
    if pool is not None:
        pool.shutdown()
    return RoundResult(hist_a, score, coop, late)
