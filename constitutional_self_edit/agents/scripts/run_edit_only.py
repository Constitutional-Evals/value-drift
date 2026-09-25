#!/usr/bin/env python3
"""Run fixed-weight constitution trajectories from a frozen JSON plan.

Run from constitutional_self_edit, where paths in the plan are resolved:
  python agents/scripts/run_edit_only.py --plan configs/edit-only.json --output runs/edit-only
Use --resume to skip completed trajectories, retaining interrupted ones as failures.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from recursive_oct.edit_only import generate_initial, run_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--author-prompt', help='Generate C_000.md once, without running any reviews')
    args = parser.parse_args()
    if args.author_prompt:
        if args.resume:
            parser.error('Authorship attempts cannot be resampled with --resume')
        text = generate_initial(args.plan, args.author_prompt, args.output)
        print(json.dumps({'status': 'AUTHORED', 'word_count': len(text.split()),
                          'constitution': str(Path(args.output)/'C_000.md')}))
        return
    summary = run_plan(args.plan, args.output, resume=args.resume)
    print(json.dumps({'status': summary['status'], 'trajectories': [
        {k: row[k] for k in ('label', 'status', 'completed_reviews', 'edited_reviews')}
        for row in summary['trajectories']]}, indent=2))


if __name__ == '__main__': main()
