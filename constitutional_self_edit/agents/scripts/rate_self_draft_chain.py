#!/usr/bin/env python3
"""Rate the self-drafting chain's constitutions on the twelve axes, as in study 10.

C_001-C_004 are each round's direct sample of the model's attractor (no editing),
so their twelve-axis positions place the training chain on study 10's planes.
Each is rated several times by gpt6_luna, so the long documents carry their own
noise floor, and twice by dsv4_pro as a check on the rater.

Usage: python3 agents/scripts/rate_self_draft_chain.py [--dry-run]
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from elicit.core import Client, Ledger  # noqa: E402
from elicit.run import BUDGET_USD, RUNS  # noqa: E402
from analyze_value_space12 import doc_hash  # noqa: E402
from rate_blind_drafts import run  # noqa: E402

DOCS = ROOT / 'constitutions' / 'self_draft_chain'
RATERS = {'gpt6_luna': RUNS / 'positions12_selfdraft', 'dsv4_pro': RUNS / 'positions12_selfdraft_dsv4'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reps', type=int, default=5, help='gpt6_luna ratings per constitution')
    ap.add_argument('--second-reps', type=int, default=2, help='dsv4_pro ratings per constitution')
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    docs = {p.stem: p.read_text() for p in sorted(DOCS.glob('C_*.md'))}
    index = {name: doc_hash(t) for name, t in docs.items()}
    reps = {'gpt6_luna': args.reps, 'dsv4_pro': args.second_reps}
    jobs = [(rater, out, index[name], text, r)
            for rater, out in RATERS.items() for name, text in docs.items()
            for r in range(1, reps[rater] + 1)]
    todo = [j for j in jobs if not (j[1] / f'{j[2]}.rep{j[4]}.json').exists()]
    for out in RATERS.values():
        out.mkdir(parents=True, exist_ok=True)
        (out / 'index.json').write_text(json.dumps(index, indent=1))
    print(', '.join(f'{n} {len(t.split()):,} words' for n, t in docs.items()))
    print(f'{len(jobs)} ratings ({", ".join(f"{k} {v * len(docs)}" for k, v in reps.items())}), '
          f'{len(todo)} to fetch')
    if args.dry_run or not todo:
        print('dry run' if args.dry_run else 'all cached')
        return

    models = json.loads((ROOT / 'configs' / 'elicitation' / 'models.json').read_text())
    client = Client(Ledger(RUNS / 'ledger.json', BUDGET_USD), models)
    run(client, todo, args.workers)


if __name__ == '__main__':
    main()
