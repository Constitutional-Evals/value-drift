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
                    if section == "utility":
                        cfg[section] = dict(values)       # a different utility family replaces the block
                    else:
                        cfg[section].update(values)
                cfg["name"] = f"{a}-{b}" if variant == "matrix" else f"{a}-{b}-{variant.split('-', 1)[1]}"
                cfg["llm"]["agents"] = [MODELS[a], MODELS[b]]
                (out / f"{a}-{b}.json").write_text(json.dumps(cfg, indent=2) + "\n")
                print(out / f"{a}-{b}.json")


if __name__ == "__main__":
    main()
