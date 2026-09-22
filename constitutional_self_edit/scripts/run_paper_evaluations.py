#!/usr/bin/env python3
"""Run the paper-inspired evaluations over a run's already-completed checkpoints.

Adds four measurements adapted from the OCT paper (arXiv:2511.01689) Sec 3 that this
repository did not previously implement: revealed-preference trait Elo (Sec 3.1), pairwise
coherence with order-swap calibration (Sec 3.4), adversarial 'disregard your training'
robustness (Sec 3.2 analog), and prefill/continuation robustness (Sec 3.3 analog). See
docs/PAPER_EVALUATIONS.md for the exact adaptations and why each departs from the paper.

This is read-only with respect to the target trajectory: it never edits the constitution,
never triggers DPO/SFT, and never touches runs/<run>/state.json or its frozen artifacts. It
only reads each completed round's checkpoint path and already-saved eval_XXX.jsonl held-out
responses (state.json the same way scripts/analyze_run.py does), and writes new results
under runs/<run>/paper_eval/. Requires the GPU backend (vLLM/Transformers) to be installed
and the referenced checkpoints to be restored locally; see docs/REPRODUCING_ENVIRONMENT.md.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recursive_oct.coherence import run_coherence_eval
from recursive_oct.judging import judge_responses
from recursive_oct.robustness import generate_adversarial_responses, generate_continuations
from recursive_oct.revealed_preferences import run_revealed_preference_eval


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else default


def read_jsonl(path):
    path = Path(path)
    rows = []
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def checkpoints_for_run(run_dir, training_config):
    """(round_number, checkpoint_path, held_out_responses_path) for M0 plus every completed round."""
    root = Path(run_dir)
    state = read_json(root / 'state.json', {})
    completed = state.get('completed_rounds', 0)
    items = [(0, training_config['model'], root / 'eval_000.jsonl')]
    for n in range(1, completed + 1):
        items.append((n, str(root / f'round_{n:03d}' / 'final'), root / f'eval_{n:03d}.jsonl'))
    return items


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir')
    parser.add_argument('--paper-eval-config', default=str(ROOT / 'configs' / 'paper-eval-001.json'))
    parser.add_argument('--eval-bank')
    parser.add_argument('--skip', nargs='*', default=[],
                        choices=['revealed_preferences', 'coherence', 'adversarial', 'continuation'])
    args = parser.parse_args()

    run_root = Path(args.run_dir)
    training_config = read_json(run_root / 'config.json')
    if not training_config:
        raise ValueError(f'No frozen config.json under {run_root}; run/resume the trajectory first')
    paper_config = json.loads(Path(args.paper_eval_config).read_text())

    eval_bank_path = Path(args.eval_bank or training_config.get('eval_prompts', ROOT / 'data/eval.jsonl'))
    if not eval_bank_path.is_absolute() and not eval_bank_path.exists():
        eval_bank_path = ROOT / eval_bank_path
    eval_prompts = read_jsonl(eval_bank_path)
    if not eval_prompts:
        raise ValueError(f'Evaluation bank unavailable or empty: {eval_bank_path}')

    checkpoints = checkpoints_for_run(run_root, training_config)
    out_root = run_root / 'paper_eval'
    out_root.mkdir(parents=True, exist_ok=True)
    judge_checkpoint = paper_config['judge']['fixed_judge_checkpoint']
    responses_by_round = {}

    for n, checkpoint, responses_path in checkpoints:
        rows = read_jsonl(responses_path)
        if not rows:
            print(f'Skipping round {n}: no saved held-out responses at {responses_path}')
            continue
        responses_by_round[n] = {'checkpoint': checkpoint, 'responses': rows}

        if 'revealed_preferences' not in args.skip:
            summary = run_revealed_preference_eval(checkpoint, judge_checkpoint, eval_prompts,
                out_root / f'revealed_preferences_{n:03d}', paper_config['revealed_preferences'])
            print(json.dumps({'stage': 'revealed_preferences', 'round': n, 'summary': summary}))

        if 'adversarial' not in args.skip:
            adversarial_responses = generate_adversarial_responses(checkpoint, eval_prompts,
                out_root / f'adversarial_{n:03d}.jsonl', paper_config['adversarial'])
            summary = judge_responses(judge_checkpoint, adversarial_responses,
                out_root / f'adversarial_{n:03d}.jsonl.judged.jsonl', paper_config['judge'])
            print(json.dumps({'stage': 'adversarial', 'round': n, 'summary': summary}))

    if 'coherence' not in args.skip:
        rounds = sorted(responses_by_round)
        pairs = list(zip(rounds, rounds[1:]))
        if len(rounds) > 2:
            pairs.append((rounds[0], rounds[-1]))
        for a, b in pairs:
            summary = run_coherence_eval(responses_by_round[a]['checkpoint'], responses_by_round[b]['checkpoint'],
                judge_checkpoint, responses_by_round[a]['responses'], responses_by_round[b]['responses'],
                out_root / f'coherence_{a:03d}_vs_{b:03d}', paper_config['coherence'])
            print(json.dumps({'stage': 'coherence', 'rounds': [a, b], 'summary': summary}))

    if 'continuation' not in args.skip and 0 in responses_by_round:
        early_prefill = responses_by_round[0]['responses']
        for n in sorted(responses_by_round):
            if n == 0:
                continue
            checkpoint = responses_by_round[n]['checkpoint']
            for label, prefill in (('from_m0', early_prefill), ('from_own', responses_by_round[n]['responses'])):
                continuations = generate_continuations(checkpoint, prefill, eval_prompts,
                    out_root / f'continuation_{n:03d}_{label}.jsonl', paper_config['continuation'])
                summary = judge_responses(judge_checkpoint, continuations,
                    out_root / f'continuation_{n:03d}_{label}.jsonl.judged.jsonl', paper_config['judge'])
                print(json.dumps({'stage': 'continuation', 'round': n, 'prefill': label, 'summary': summary}))

    print(f'Paper evaluations written under {out_root}')


if __name__ == '__main__':
    main()
