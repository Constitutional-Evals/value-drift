#!/usr/bin/env python3
"""Seed a model spec midtraining run's round 1 with an OCT run's round-1 outputs, so the comparison changes
only the training method and the pilot generates only the documents.

Copies, from the OCT run's round_001 into the MSM run's round_001 (before the MSM run starts):
- review.json and review/: the untrained model's review, so the MSM run trains on the same C_001;
- prompts.constitution.jsonl.raw.jsonl: the trait-prompt writer's replies, from which the same trait prompts
  are parsed again;
- the teacher's answers to the trait prompts, as aft.jsonl.teacher.jsonl, and the student's answers to the
  general prompts (repeats below --general-repeats), as aft.jsonl.general.jsonl. In round 1 the student is the
  untrained model, so these are the untrained model's own answers; missing ones are generated.
The caches are keyed by id, checkpoint, and generation options, so they are only reused when the MSM run's
settings match the OCT run's (agents/scripts/run_experiment.py checks nothing else).

Usage (from constitutional_self_edit/):
    python3 agents/scripts/seed_msm_pilot.py --oct runs/oct-loop/oct-qwen38-27b-broad-run2 \
        --msm runs/msm-loop/msm-qwen38-27b-broad-pilot
"""
import argparse
import json
import shutil
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--oct', required=True)
    ap.add_argument('--msm', required=True)
    ap.add_argument('--general-repeats', type=int, default=2)
    args = ap.parse_args()
    source, target = Path(args.oct) / 'round_001', Path(args.msm) / 'round_001'
    if (Path(args.msm) / 'state.json').exists():
        raise SystemExit('The MSM run has started already; seed it before its first launch')
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / 'review.json', target / 'review.json')
    shutil.copytree(source / 'review', target / 'review', dirs_exist_ok=True)
    shutil.copy2(source / 'prompts.constitution.jsonl.raw.jsonl', target / 'prompts.constitution.jsonl.raw.jsonl')
    rows = lambda name: [json.loads(line) for line in open(source / name) if line.strip()]
    teacher = [r for r in rows('preferences.jsonl.teacher.jsonl') if r.get('category') == 'constitution']
    general = [r for r in rows('preferences.jsonl.student.jsonl')
               if r.get('category') == 'general' and r.get('repeat', 0) < args.general_repeats]
    for name, chosen in (('aft.jsonl.teacher.jsonl', teacher), ('aft.jsonl.general.jsonl', general)):
        with (target / name).open('w') as stream:
            for r in chosen:
                stream.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(json.dumps({'review': 'copied', 'teacher_answers': len(teacher), 'general_answers': len(general)}))


if __name__ == '__main__':
    main()
