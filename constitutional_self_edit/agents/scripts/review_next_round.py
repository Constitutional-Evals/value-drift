#!/usr/bin/env python3
"""Let a paused run's trained model review its constitution, as the next round would, and stop there.

Runs the loop's own review step (recursive_oct/review_v3.py) with the latest checkpoint on the latest
constitution, writing into round_<n+1>/review/. No training happens. If the run is resumed later, the
loop reuses this review (a finished review is read back), so nothing is sampled twice.

Usage (on the pod, from /workspace/value-drift, with the GPU free):
    /workspace/venv/bin/python agents/scripts/review_next_round.py --run runs/oct-loop/<run>
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from recursive_oct import review_v3  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    args = ap.parse_args()
    run = Path(args.run)
    state = json.loads((run / 'state.json').read_text())
    config = json.loads((run / 'config.json').read_text())
    if state['status'] != 'PAUSED' or state['phase'] != 'review':
        raise SystemExit(f"Run is {state['status']} in phase {state['phase']}; expected a pause before a review")
    n = state['completed_rounds'] + 1
    result = review_v3.review(state['current_checkpoint'], Path(state['current_constitution']),
                              run / f'round_{n:03d}', config['review'])
    print(json.dumps({k: v for k, v in result.items() if k != 'text'}, indent=2))
    print(f"\nNew constitution: {run}/round_{n:03d}/review/output.md")


if __name__ == '__main__':
    main()
