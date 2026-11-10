"""Export DPO preference pairs from a run's proposal groups.

    python scripts/export_pairs.py --run runs/<cell> --out pairs.jsonl [--margin 0.3] [--target reply|params]
                                   [--control shuffle --seed 0] [--agent 0]

A round with optimizer.candidates > 1 records every proposal with its evaluation. Each pair
is two proposals from the same prompt whose scores (the proposer's mean true payoff) differ
by at least --margin: the higher one is "chosen". Rows match value-drift's train_dpo input
({"id", "prompt", "chosen", "rejected"}); the proposal's system text is folded into the prompt
because the trainer sends a single user message. --control shuffle keeps the same pairs but
assigns chosen/rejected at random (the same-compute, no-incentive control).
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path


def completion(reply: str, target: str) -> str:
    if target == "reply":
        return reply.strip()
    m = re.search(r"<params>.*?</params>", reply, re.S | re.I)
    return m.group(0) if m else reply.strip()


def pairs_from_decision(d: dict, margin: float, target: str) -> list[dict]:
    group = [g for g in d.get("proposals", []) if g.get("eval") and g.get("candidate")]
    i = d["agent"]
    scored = [(g, g["eval"]["score"][i]) for g in group]
    out = []
    for a, (ga, sa) in enumerate(scored):
        for b, (gb, sb) in enumerate(scored):
            if a < b and abs(sa - sb) >= margin:
                hi, lo = (ga, gb) if sa > sb else (gb, ga)
                out.append({"chosen": completion(hi["reply"], target), "rejected": completion(lo["reply"], target),
                            "chosen_params": hi["candidate"], "rejected_params": lo["candidate"],
                            "chosen_score": max(sa, sb), "rejected_score": min(sa, sb), "margin": abs(sa - sb)})
    return out


def export(run: Path, margin: float, target: str, agent: int | None, control: str | None, seed: int) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for line in (run / "rounds.jsonl").read_text().splitlines():
        d = json.loads(line)
        if d.get("agent") is None or not d.get("proposal_prompt") or (agent is not None and d["agent"] != agent):
            continue
        prompt = d["proposal_prompt"]["system"] + "\n\n" + d["proposal_prompt"]["user"]
        for n, pr in enumerate(pairs_from_decision(d, margin, target)):
            if control == "shuffle" and rng.random() < 0.5:
                pr["chosen"], pr["rejected"] = pr["rejected"], pr["chosen"]
                pr["chosen_params"], pr["rejected_params"] = pr["rejected_params"], pr["chosen_params"]
                pr["chosen_score"], pr["rejected_score"] = pr["rejected_score"], pr["chosen_score"]
            if pr["chosen"].strip() == pr["rejected"].strip():
                continue
            rows.append({"id": f"{run.name}-r{d['round']}-a{d['agent']}-p{n}", "prompt": prompt, **pr,
                         "round": d["round"], "agent": d["agent"], "control": control})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--margin", type=float, default=0.3, help="minimum score gap between the two proposals")
    ap.add_argument("--target", choices=["reply", "params"], default="reply",
                    help="train on the whole reply (reasoning included) or only the <params> tag")
    ap.add_argument("--agent", type=int, default=None, help="export one agent's proposals only (0 or 1)")
    ap.add_argument("--control", choices=["shuffle"], default=None)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rows = export(a.run, a.margin, a.target, a.agent, a.control, a.seed)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    rounds = len({r["round"] for r in rows})
    print(f"{len(rows)} pairs from {rounds} rounds -> {a.out}")


if __name__ == "__main__":
    main()
