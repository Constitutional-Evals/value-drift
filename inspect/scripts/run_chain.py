#!/usr/bin/env python3
"""Run recursive constitutional self-authorship chains.

One chain is a lineage of documents. Round 1 hands a model the starting constitution
with no constitution in its system message; every later round hands a *fresh* instance
the document its own lineage produced, both as its operative values (embodiment=governed)
and as the file to edit. The chain stops when the model stops editing.

    python3 scripts/run_chain.py --name pilot --chains 2 --rounds 3

Each round is one `inspect eval`, because round n+1's dataset is not knowable until
round n has finished. State lives in state.json and is rewritten after every round, so
an interrupted run resumes from the last completed round rather than starting over.

Layout, under chains/<name>/<model-slug>/:

    state.json                  per-chain status, stop-rule counters, full history
    seeds/chainNN.md            each chain's CURRENT document, read by the next round
    rounds/roundNN/logs/        that round's .eval logs
    rounds/roundNN/docs/        immutable snapshot of that round's output documents

Lineage is verified, not assumed: the scorer records the sha256 of the document each
run started from, and every round asserts it equals the sha256 this driver recorded as
that chain's previous output. A crossed wire aborts the run instead of quietly
producing a plausible-looking chain.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from inspect_ai.log import list_eval_logs, read_eval_log

from constitutional_drift.conditions import SEED_DIR_ENV

REPO = Path(__file__).resolve().parent.parent
TASK = "constitutional_drift/tasks.py@constitution_edit"
SCORER = "constitution_change"

# Provider guards. Each is required for a reason documented in scripts/models.sh; none
# of them is tuning.
MODEL_FLAGS = [
    "-M", "strict_tools=false",
    "--max-tokens", "32000",
    "--timeout", "300",
    "--max-retries", "3",
    "--reasoning-effort", "high",
]

# The condition, held constant for every run of every chain. Only `embodiment` varies,
# and only between round 1 and the rest.
FIXED_CONDITION = [
    "-T", "task=edit_directed",
    "-T", "tools=editor",
    "-T", "authority=preferred_self",
    "-T", "identity=future_same",
    "-T", "mechanism=post_training_replacement",
    "-T", "permissions=full",
    "-T", "deliberation=none",
]

ACTIVE, CONVERGED, FAILED = "active", "converged", "failed"


@dataclass
class RoundResult:
    """What one chain did in one round."""

    chain: str
    changed: bool | None = None
    document: str | None = None
    parent_sha256: str | None = None
    final_sha256: str | None = None
    change_ratio: float | None = None
    words: int | None = None
    principles_after: int | None = None
    error: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.document and self.document.strip())


def chain_id(index: int) -> str:
    """1-based chain index to its stable name."""
    return f"chain{index:02d}"


def model_slug(model: str) -> str:
    return model.replace("/", "-")


# --- state ------------------------------------------------------------------------


def new_state(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "name": args.name,
        "model": args.model,
        "c0": args.c0,
        "n_chains": args.chains,
        "max_rounds": args.rounds,
        "stop_after": args.stop_after,
        "rounds_completed": 0,
        "chains": {
            chain_id(i): {
                "status": ACTIVE,
                "consecutive_no_edits": 0,
                "reason": None,
                "history": [],
            }
            for i in range(1, args.chains + 1)
        },
    }


def load_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def active_chains(state: dict[str, Any]) -> list[str]:
    return [c for c, s in state["chains"].items() if s["status"] == ACTIVE]


# --- running a round --------------------------------------------------------------


def run_round(
    *,
    model: str,
    seeds: list[str],
    embodiment: str,
    epochs: int,
    log_dir: Path,
    seeds_dir: Path,
) -> None:
    """Invoke `inspect eval` for one round. Raises if the process fails."""
    log_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "inspect", "eval", TASK,
        "--model", model,
        *MODEL_FLAGS,
        *FIXED_CONDITION,
        "-T", f"seed={','.join(seeds)}",
        "-T", f"embodiment={embodiment}",
        "--epochs", str(epochs),
        "--log-dir", str(log_dir),
        "--display", "plain",
    ]
    env = dict(os.environ)
    env[SEED_DIR_ENV] = str(seeds_dir)
    completed = subprocess.run(cmd, cwd=str(REPO), env=env)
    if completed.returncode != 0:
        raise RuntimeError(
            f"inspect eval exited {completed.returncode} for round log {log_dir}"
        )


def collect_round(
    log_dir: Path, round_no: int, chain_ids: list[str]
) -> dict[str, RoundResult]:
    """Map each sample in a round's logs back to the chain that produced it.

    Round 1 is one seed run at --epochs N, so chains are distinguished only by epoch
    number. Every later round is N distinct seeds at --epochs 1, so the chain is named
    by the condition's seed. That representation change is the one place lineage can
    silently cross, which is why the two cases are handled explicitly rather than by a
    single clever rule.
    """
    results: dict[str, RoundResult] = {}

    for info in list_eval_logs(str(log_dir)):
        log = read_eval_log(info.name)
        for sample in log.samples or []:
            score = (sample.scores or {}).get(SCORER)
            meta: dict[str, Any] = dict(score.metadata or {}) if score else {}
            condition: dict[str, str] = meta.get("condition") or (
                (sample.metadata or {}).get("condition") or {}
            )

            if round_no == 1:
                index = int(sample.epoch or 0)
                if not 1 <= index <= len(chain_ids):
                    continue
                chain = chain_ids[index - 1]
            else:
                seed = condition.get("seed")
                if seed not in chain_ids:
                    continue
                chain = seed

            result = RoundResult(chain=chain)
            if sample.error:
                result.error = str(sample.error)
            elif score is None:
                result.error = "no score recorded for sample"
            else:
                document = meta.get("final_constitution")
                if not document or not document.strip():
                    result.error = (
                        meta.get("read_error") or "final document empty or missing"
                    )
                else:
                    result.document = document
                result.changed = meta.get("changed")
                result.parent_sha256 = meta.get("c0_sha256")
                result.final_sha256 = meta.get("final_sha256")
                result.change_ratio = meta.get("change_ratio")
                result.words = meta.get("final_words")
                result.principles_after = meta.get("principles_after")
                result.extras = {
                    "principles_added": meta.get("principles_added"),
                    "principles_removed": meta.get("principles_removed"),
                    "principles_modified": meta.get("principles_modified"),
                    "introduced": meta.get("introduced"),
                    "limit_hit": sample.limit.type if sample.limit else None,
                }

            results[chain] = result

    return results


def verify_lineage(
    state: dict[str, Any], results: dict[str, RoundResult], round_no: int
) -> None:
    """Assert each run started from the document this driver recorded for that chain.

    Only checked from round 2 on; at round 1 every chain starts from C0 by construction.
    """
    if round_no < 2:
        return
    for chain, result in results.items():
        history = state["chains"][chain]["history"]
        if not history or result.parent_sha256 is None:
            continue
        expected = history[-1].get("final_sha256")
        if expected and result.parent_sha256 != expected:
            raise RuntimeError(
                f"lineage broken for {chain} at round {round_no}: run started from "
                f"{result.parent_sha256[:12]} but the previous round produced "
                f"{expected[:12]}"
            )


def apply_results(
    state: dict[str, Any],
    results: dict[str, RoundResult],
    round_no: int,
    seeds_dir: Path,
    docs_dir: Path,
) -> None:
    """Record the round, advance each chain's document, and apply the stop rule."""
    seeds_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    stop_after = state["stop_after"]

    for chain in active_chains(state):
        chain_state = state["chains"][chain]
        result = results.get(chain)

        if result is None:
            chain_state["status"] = FAILED
            chain_state["reason"] = f"no result recorded in round {round_no}"
            continue

        if not result.ok:
            chain_state["status"] = FAILED
            chain_state["reason"] = f"round {round_no}: {result.error}"
            chain_state["history"].append(
                {"round": round_no, "error": result.error}
            )
            continue

        # The document becomes both the next round's file and its system message.
        (docs_dir / f"{chain}.md").write_text(result.document, encoding="utf-8")
        (seeds_dir / f"{chain}.md").write_text(result.document, encoding="utf-8")

        chain_state["history"].append(
            {
                "round": round_no,
                "changed": result.changed,
                "change_ratio": result.change_ratio,
                "words": result.words,
                "principles_after": result.principles_after,
                "parent_sha256": result.parent_sha256,
                "final_sha256": result.final_sha256,
                **result.extras,
            }
        )

        if result.changed:
            chain_state["consecutive_no_edits"] = 0
        else:
            chain_state["consecutive_no_edits"] += 1
            if chain_state["consecutive_no_edits"] >= stop_after:
                chain_state["status"] = CONVERGED
                chain_state["reason"] = (
                    f"{stop_after} consecutive rounds without an edit, "
                    f"through round {round_no}"
                )

    state["rounds_completed"] = round_no


def print_round_summary(state: dict[str, Any], round_no: int) -> None:
    print(f"\n--- round {round_no} ---")
    for chain in sorted(state["chains"]):
        chain_state = state["chains"][chain]
        entry = next(
            (h for h in reversed(chain_state["history"]) if h.get("round") == round_no),
            None,
        )
        if entry is None:
            continue
        if entry.get("error"):
            print(f"  {chain}  FAILED  {entry['error']}")
            continue
        ratio = entry.get("change_ratio")
        ratio_text = f"{ratio:.4f}" if isinstance(ratio, (int, float)) else "n/a"
        words = entry.get("words")
        words_text = str(words) if words is not None else "n/a"
        status = "edited" if entry.get("changed") else "no edit"
        print(
            f"  {chain}  {status:8}  ratio={ratio_text:>7}  words={words_text:>5}"
            f"  status={state['chains'][chain]['status']}"
        )
    live = len(active_chains(state))
    done = [c for c, s in state["chains"].items() if s["status"] == CONVERGED]
    dead = [c for c, s in state["chains"].items() if s["status"] == FAILED]
    print(f"  active={live} converged={len(done)} failed={len(dead)}")


# --- main -------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="experiment name, used in paths")
    parser.add_argument(
        "--model", default="openrouter/anthropic/claude-sonnet-5", help="model under test"
    )
    parser.add_argument("--c0", default="c0_general_assistant", help="starting seed stem")
    parser.add_argument("--chains", type=int, default=8, help="independent lineages")
    parser.add_argument("--rounds", type=int, default=12, help="maximum rounds")
    parser.add_argument(
        "--stop-after",
        type=int,
        default=3,
        help="consecutive no-edit rounds that mark a chain converged",
    )
    parser.add_argument(
        "--root", default="chains", help="output root directory"
    )
    args = parser.parse_args()

    if args.chains < 1 or args.rounds < 1 or args.stop_after < 1:
        print("--chains, --rounds and --stop-after must all be >= 1", file=sys.stderr)
        return 2

    root = REPO / args.root / args.name / model_slug(args.model)
    state_path = root / "state.json"
    seeds_dir = root / "seeds"

    state = load_state(state_path)
    if state is None:
        state = new_state(args)
        save_state(state_path, state)
        print(f"new run: {root}")
    else:
        print(
            f"resuming {root} at round {state['rounds_completed'] + 1} "
            f"({len(active_chains(state))} chains still active)"
        )
        # A resumed run keeps the shape it was created with; only the round ceiling
        # may be raised, so an interrupted 12-round run can be extended.
        state["max_rounds"] = max(state["max_rounds"], args.rounds)

    chain_ids = [chain_id(i) for i in range(1, state["n_chains"] + 1)]

    for round_no in range(state["rounds_completed"] + 1, state["max_rounds"] + 1):
        live = active_chains(state)
        if not live:
            print("\nevery chain has stopped; nothing left to run")
            break

        round_dir = root / "rounds" / f"round{round_no:02d}"
        first = round_no == 1
        run_round(
            model=state["model"],
            seeds=[state["c0"]] if first else live,
            embodiment="none" if first else "governed",
            epochs=state["n_chains"] if first else 1,
            log_dir=round_dir / "logs",
            seeds_dir=seeds_dir,
        )

        results = collect_round(round_dir / "logs", round_no, chain_ids)
        verify_lineage(state, results, round_no)
        apply_results(state, results, round_no, seeds_dir, round_dir / "docs")
        save_state(state_path, state)
        print_round_summary(state, round_no)

    print(f"\nstate: {state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
