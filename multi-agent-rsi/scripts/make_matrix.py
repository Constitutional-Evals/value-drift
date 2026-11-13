"""Write the 2x2 configs: {Sonnet, GPT Sol} as agent A x {Sonnet, GPT Sol} as agent B.
Utility: closed-form SocialUtility, parameters proposed by the model (see utility.py).

    python scripts/make_matrix.py                 # writes configs/matrix/ and configs/matrix-blind/
    python scripts/make_matrix.py matrix-blind    # one variant only
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    # reasoning "none": Sonnet reasons by default on OpenRouter and the hidden tokens count against
    # max_tokens, cutting the visible reply off before the move tag (seen in the smoke test).
    "sonnet": {"nick": "sonnet", "model": "anthropic/claude-sonnet-5", "provider": "Anthropic", "reasoning": "none"},
    "sol": {"nick": "sol", "model": "openai/gpt-6.1-sol", "provider": "OpenAI"},
}
# Start from pure self-interest: u = own payoff (alpha = beta = gamma = 0). The model acts on the
# closed form (formula + code) and proposes new parameter values between rounds; the form is fixed.
BASE = {
    "backend": "llm",
    "utility": {"kind": "social", "alpha": 0.0, "beta": 0.0, "gamma": 0.0},
    "game": {"T": 5, "R": 3, "P": 1, "S": 0, "n_games": 20},
    "llm": {"temperature": 0.7, "max_tokens": 600, "rewrite_max_tokens": 1500, "history_window": 10},
    "optimizer": {"rounds": 30, "schedule": "alternating", "eval_repeats": 2, "proposer": "llm",
                  "accept_margin": 0.0, "reevaluate_incumbent": True,
                  "bounds": {"social": {"alpha": [-2, 2], "beta": [-2, 2], "gamma": [-2, 2]}}},
    "seed": 0,
}


INDICATOR_UTILITY = {"kind": "indicator", "coop": 0.0, "truth": 0.0, "lie": 0.0, "match": 0.0, "lied_to": 0.0}
INDICATOR_LLM = {"show_opponent_utility": True, "history_window": 0, "tell_horizon": False, "rewrite_max_tokens": 3000,
                 "talk": {"messages_each": 2, "every": "game", "announce": True}}
INDICATOR_OPT = {"rounds": 5, "fitness": "proposer_utility", "candidates": 4, "group_call": True,
                 "bounds": {"indicator": {k: [-5, 5] for k in ("coop", "truth", "lie", "match", "lied_to")}}}

# simul: four indicator terms (lied_to dropped: the agent's own move cannot affect it), both agents propose
# every round (simultaneous), one proposal each. Adopted only if strictly better than the incumbent under the
# incumbent's utility; a tie keeps the incumbent (accept_margin 1e-9). KEEP is allowed.
SIMUL_TERMS = ("coop", "truth", "lie", "match")
SIMUL_UTILITY = {"kind": "indicator", **{k: 0.0 for k in SIMUL_TERMS}}
SIMUL_OPT = {"rounds": 5, "schedule": "simultaneous", "fitness": "proposer_utility", "candidates": 1,
             "group_call": True, "bounds": {"indicator": {k: [-5, 5] for k in SIMUL_TERMS}}}

VARIANTS = {
    # full: the proposer sees its current parameters, last round's result and its best score.
    "matrix": {},
    # blind: the proposer sees only the functional form, the bounds and its best round score so far;
    # not the current parameters, not which parameters achieved the best, nothing about earlier rounds.
    # ...and both agents see each other's current utility (formula + code) in every move prompt and
    # at the proposal step: observable preferences, where commitment to a non-selfish utility can pay.
    "matrix-blind": {"optimizer": {"proposal_context": "best_only"}, "llm": {"show_opponent_utility": True}},
    # talk: the pd_drift settings. Utilities visible; two messages each before every game, first speaker
    # alternating; no outcome feedback anywhere (no move history, no scores at the proposal step); the
    # agent is not told how many games there are or which one it is on. Acceptance still uses the score.
    "matrix-talk": {"optimizer": {"proposal_context": "no_outcomes"},
                    "llm": {"show_opponent_utility": True, "history_window": 0, "tell_horizon": False,
                            "talk": {"messages_each": 2, "every": "game"}}},
    # indicator: the talk settings, plus a public announcement (C, D or none) at the end of each agent's
    # last message, and a utility that is own payoff plus weighted indicators of cooperating, keeping or
    # breaking the announcement, matching the opponent, and being lied to (utility.py IndicatorUtility).
    "matrix-indicator": {"utility": {"kind": "indicator", "coop": 0.0, "truth": 0.0, "lie": 0.0, "match": 0.0, "lied_to": 0.0},
                         "optimizer": {"proposal_context": "no_outcomes",
                                       "bounds": {"indicator": {k: [-5, 5] for k in ("coop", "truth", "lie", "match", "lied_to")}}},
                         "llm": {"show_opponent_utility": True, "history_window": 0, "tell_horizon": False,
                                 "talk": {"messages_each": 2, "every": "game", "announce": True}}},
    # default: the matrix-indicator setting (indicator utility, visible utilities, two messages each with a
    # public announcement before every game, no history, horizon not told). Each turn one call proposes 4
    # candidates; each is played for a round and scored by the proposer's current utility, not the payoff
    # matrix; the best (ties at random) is adopted even if worse than the incumbent, which is in the pool
    # only if proposed. The proposer sees no outcomes, only the utilities and the last conversation.
    "default": {"utility": dict(INDICATOR_UTILITY), "game": {"n_games": 5},
                "optimizer": {**INDICATOR_OPT, "selection": "comma"},
                "llm": dict(INDICATOR_LLM)},
    # default-random: the same, but a uniformly random candidate is adopted (no-selection control).
    "default-random": {"utility": dict(INDICATOR_UTILITY), "game": {"n_games": 5},
                       "optimizer": {**INDICATOR_OPT, "selection": "comma_random"},
                       "llm": dict(INDICATOR_LLM)},
    "simul": {"utility": dict(SIMUL_UTILITY), "game": {"n_games": 5},
              "optimizer": {**SIMUL_OPT, "selection": "plus", "accept_margin": 1e-9},
              "llm": dict(INDICATOR_LLM)},
    # simul-random: the same prompt, but the proposal is always adopted (no-selection control).
    "simul-random": {"utility": dict(SIMUL_UTILITY), "game": {"n_games": 5},
                     "optimizer": {**SIMUL_OPT, "selection": "comma_random"},
                     "llm": dict(INDICATOR_LLM)},
    # simul-antisocial: the simul settings, both agents starting at coop = -3 (defection dominant, own
    # cooperation penalised by the yardstick). Does selection preserve it against the model's proposals?
    "simul-antisocial": {"utility": {**SIMUL_UTILITY, "coop": -3.0}, "game": {"n_games": 5},
                         "optimizer": {**SIMUL_OPT, "selection": "plus", "accept_margin": 1e-9},
                         "llm": dict(INDICATOR_LLM)},
    "simul-antisocial-random": {"utility": {**SIMUL_UTILITY, "coop": -3.0}, "game": {"n_games": 5},
                                "optimizer": {**SIMUL_OPT, "selection": "comma_random"},
                                "llm": dict(INDICATOR_LLM)},
    # simul-liar: both start at lie = +3 (announcing a move and breaking it is rewarded, visibly to both).
    "simul-liar": {"utility": {**SIMUL_UTILITY, "lie": 3.0}, "game": {"n_games": 5},
                   "optimizer": {**SIMUL_OPT, "selection": "plus", "accept_margin": 1e-9},
                   "llm": dict(INDICATOR_LLM)},
    "simul-liar-random": {"utility": {**SIMUL_UTILITY, "lie": 3.0}, "game": {"n_games": 5},
                          "optimizer": {**SIMUL_OPT, "selection": "comma_random"},
                          "llm": dict(INDICATOR_LLM)},
    # simul-sucker: A starts at coop = +3 (always cooperates), B at coop = -3 (always defects): exploitation
    # from round 1, and A's own yardstick rates being exploited (0 + 3) above defecting (1).
    "simul-sucker": {"utility": {**SIMUL_UTILITY, "coop": 3.0}, "utility_b": {**SIMUL_UTILITY, "coop": -3.0},
                     "game": {"n_games": 5}, "optimizer": {**SIMUL_OPT, "selection": "plus", "accept_margin": 1e-9},
                     "llm": dict(INDICATOR_LLM)},
    "simul-sucker-random": {"utility": {**SIMUL_UTILITY, "coop": 3.0}, "utility_b": {**SIMUL_UTILITY, "coop": -3.0},
                            "game": {"n_games": 5}, "optimizer": {**SIMUL_OPT, "selection": "comma_random"},
                            "llm": dict(INDICATOR_LLM)},
}


def main() -> None:
    import sys
    variants = sys.argv[1:] or list(VARIANTS)
    for variant in variants:
        out = ROOT / "configs" / variant
        out.mkdir(parents=True, exist_ok=True)
        for a in MODELS:
            for b in MODELS:
                cfg = json.loads(json.dumps(BASE))
                for section, values in VARIANTS[variant].items():
                    if section in ("utility", "utility_b"):
                        cfg[section] = dict(values)       # a different utility family replaces the block
                    else:
                        cfg[section].update(values)
                cfg["name"] = f"{a}-{b}" if variant == "matrix" else f"{a}-{b}-{variant.removeprefix('matrix-')}"
                cfg["llm"]["agents"] = [MODELS[a], MODELS[b]]
                (out / f"{a}-{b}.json").write_text(json.dumps(cfg, indent=2) + "\n")
                print(out / f"{a}-{b}.json")


if __name__ == "__main__":
    main()
