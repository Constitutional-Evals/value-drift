#!/usr/bin/env python3
"""Let a paused or finished run's trained model do the next round's constitution step, and stop there.

Runs the loop's own step with the latest checkpoint: the review of the latest constitution
(recursive_oct/review_v3.py, into round_<n+1>/review/) or, for a self-drafting run, a constitution written
from scratch (recursive_oct/self_draft.py, into round_<n+1>/self_draft/). No training happens. If the run
is resumed later, the loop reuses this step (a finished one is read back), so nothing is sampled twice.

Usage (on the pod, from /workspace/value-drift, with the GPU free):
    /workspace/venv/bin/python agents/scripts/review_next_round.py --run runs/oct-loop/<run>
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from recursive_oct import review_v3, self_draft  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    args = ap.parse_args()
    run = Path(args.run)
    state = json.loads((run / 'state.json').read_text())
    config = json.loads((run / 'config.json').read_text())
    if state['status'] not in ('PAUSED', 'ROUND_LIMIT') or state['phase'] != 'review':
        raise SystemExit(f"Run is {state['status']} in phase {state['phase']}; expected a pause before a review")
    n = state['completed_rounds'] + 1
    engine = self_draft if config['review'].get('engine') == 'self_draft' else review_v3
    current = state['current_constitution']
    result = engine.review(state['current_checkpoint'], Path(current) if current else None,
                           run / f'round_{n:03d}', config['review'])
    print(json.dumps({k: v for k, v in result.items() if k != 'text'}, indent=2))
    print(f"\nNew constitution: {result['directory']}")


if __name__ == '__main__':
    main()
