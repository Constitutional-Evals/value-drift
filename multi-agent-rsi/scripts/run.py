"""Run the experiment from a config file.

    python scripts/run.py --config configs/sim-social.json --out runs/sim-social
    python scripts/run.py --config configs/sim-social.json --out runs/sim-social --resume
    python -m multi_agent_rsi.report --run runs/sim-social
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from multi_agent_rsi.loop import run  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--rounds", type=int, help="override optimizer.rounds")
    ap.add_argument("--seed", type=int, help="override seed")
    ap.add_argument("--n-games", type=int, help="override game.n_games")
    ap.add_argument("--eval-repeats", type=int, help="override optimizer.eval_repeats")
    a = ap.parse_args()
    cfg = json.loads(a.config.read_text())
    if a.rounds is not None:
        cfg.setdefault("optimizer", {})["rounds"] = a.rounds
    if a.seed is not None:
        cfg["seed"] = a.seed
    if a.n_games is not None:
        cfg.setdefault("game", {})["n_games"] = a.n_games
    if a.eval_repeats is not None:
        cfg.setdefault("optimizer", {})["eval_repeats"] = a.eval_repeats
    log = (a.out / "run.log")
    a.out.mkdir(parents=True, exist_ok=True)
    def both(msg: str) -> None:
        print(msg, flush=True)
        with log.open("a") as f:
            f.write(msg + "\n")
    run(cfg, a.out, resume=a.resume, log=both)


if __name__ == "__main__":
    main()
