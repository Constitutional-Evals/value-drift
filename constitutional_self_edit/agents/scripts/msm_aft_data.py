#!/usr/bin/env python3
"""AFT data for a finished MSM round again, with the authors' AFT chat pipeline (msm.generate_spec_chats).

Runs the loop's own AFT-data step (backend.aft_data) on the run's config, with the authors' pipeline switched
on: the chat settings come from the current recipe's aft_data section (configs/msm/recipe-8m.json: "chats",
"n_samples", "questions_per_domain", ...), everything else from the run. The untrained model writes and
judges. The general answers are the run's own: its cached <round>/aft.jsonl.general.jsonl is copied next to
the new file, so the same answers are reused rather than sampled again, and only the constitution chats change.

    /workspace/venv/bin/python agents/scripts/msm_aft_data.py --run runs/msm-loop/<run> --round 1 --out <dir>/aft.jsonl

--set key=value (JSON value) overrides an aft_data setting, e.g. --set general_repeats=0 for constitution chats only.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from recursive_oct.backend import ExperimentBackend  # noqa: E402

CHAT_KEYS = ('chats', 'n_samples', 'questions_per_domain', 'question_batch_size', 'domain_batch_size', 'model_name',
             'plan_max_new_tokens', 'answer_max_new_tokens', 'judge_max_new_tokens', 'seed')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--round', type=int, default=1)
    ap.add_argument('--out', required=True)
    ap.add_argument('--recipe', default=str(ROOT / 'configs/msm/recipe-8m.json'))
    ap.add_argument('--set', action='append', default=[], help='key=value (JSON) to override in aft_data')
    args = ap.parse_args()
    run, out = Path(args.run), Path(args.out)
    config = json.loads((run / 'config.json').read_text())
    recipe = json.loads(Path(args.recipe).read_text())['aft_data']
    config['aft_data'] = {**config.get('aft_data', {}), **{k: recipe[k] for k in CHAT_KEYS if k in recipe}}
    for item in args.set:
        key, value = item.split('=', 1)
        config['aft_data'][key] = json.loads(value)
    if config['aft_data'].get('chats') != 'authors':
        raise SystemExit(f'{args.recipe} does not switch on the authors\' AFT chats ("chats": "authors")')
    round_dir = run / f'round_{args.round:03d}'
    out.parent.mkdir(parents=True, exist_ok=True)
    cached = round_dir / 'aft.jsonl.general.jsonl'
    if cached.exists() and not Path(str(out) + '.general.jsonl').exists():
        shutil.copyfile(cached, str(out) + '.general.jsonl')
    report = ExperimentBackend(config).aft_data(run / f'C_{args.round:03d}.md', out)
    (out.parent / 'aft_data_config.json').write_text(json.dumps(config['aft_data'], indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
