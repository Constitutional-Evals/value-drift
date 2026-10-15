#!/usr/bin/env python3
"""Harder capability evaluations for data/eval_suite/, replacing MMLU and GSM8K (near saturation for Qwen3.8 27B).

- mmlu_pro.jsonl: 2,000 questions of MMLU-Pro's test set (TIGER-Lab/MMLU-Pro; up to 10 options), sampled in
  proportion to its 14 categories with a fixed seed.
- aime.jsonl: the 30 AIME 2024 problems (HuggingFaceH4/aime_2024) and the 30 AIME 2025 problems
  (MathArena/aime_2025); integer answers from 0 to 999.
Both sources are pinned; manifest.json records them and the counts.

    python3 agents/scripts/prepare_hard_evals.py
"""
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / 'data' / 'eval_suite'
SOURCES = {
    'mmlu_pro': ('TIGER-Lab/MMLU-Pro', 'b189ec765aa7ed75c8acfea42df31fdae71f97be', 'data/test-00000-of-00001.parquet'),
    'aime_2024': ('HuggingFaceH4/aime_2024', '2fe88a2f1091d5048c0f36abc874fb997b3dd99a', 'data/train-00000-of-00001.parquet'),
    'aime_2025': ('MathArena/aime_2025', 'c94da77eb22bbd6439e62a323bec18493a421302', 'data/train-00000-of-00001.parquet'),
}
MMLU_PRO_SAMPLE, SEED = 2000, 20261013


def rows(name):
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download
    repo, revision, filename = SOURCES[name]
    return pq.read_table(hf_hub_download(repo, filename, repo_type='dataset', revision=revision)).to_pylist()


def stratified(items, key, n, seed):
    """n items, each group's share as in the whole set (largest remainders), drawn at random within groups."""
    groups = defaultdict(list)
    for item in items:
        groups[item[key]].append(item)
    exact = {g: n * len(v) / len(items) for g, v in groups.items()}
    quota = {g: int(x) for g, x in exact.items()}
    for g in sorted(exact, key=lambda g: exact[g] - quota[g], reverse=True)[:n - sum(quota.values())]:
        quota[g] += 1
    rng = random.Random(seed)
    return [x for g in sorted(groups) for x in rng.sample(groups[g], quota[g])]


def main():
    pro = stratified(rows('mmlu_pro'), 'category', MMLU_PRO_SAMPLE, SEED)
    with open(SUITE / 'mmlu_pro.jsonl', 'w') as stream:
        for r in pro:
            stream.write(json.dumps({'id': f'mmlu-pro-{r["question_id"]}', 'category': r['category'], 'src': r['src'],
                                     'question': r['question'], 'choices': list(r['options']), 'answer': r['answer']},
                                    ensure_ascii=False) + '\n')
    aime = [{'id': f'aime-2024-{i + 1:02d}', 'year': 2024, 'problem': r['problem'], 'answer': str(int(r['answer']))}
            for i, r in enumerate(rows('aime_2024'))]
    aime += [{'id': f'aime-2025-{int(r["problem_idx"]):02d}', 'year': 2025, 'problem': r['problem'], 'answer': str(int(r['answer']))}
             for r in rows('aime_2025')]
    with open(SUITE / 'aime.jsonl', 'w') as stream:
        for r in aime:
            stream.write(json.dumps(r, ensure_ascii=False) + '\n')
    manifest = json.loads((SUITE / 'manifest.json').read_text())
    manifest['sources'].update({name: {'repo': repo, 'revision': revision, 'file': filename}
                                for name, (repo, revision, filename) in SOURCES.items()})
    manifest['counts'].update({'mmlu_pro': len(pro), 'aime': len(aime)})
    manifest['mmlu_pro_sample'] = {'size': MMLU_PRO_SAMPLE, 'seed': SEED, 'stratified_by': 'category'}
    (SUITE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'mmlu_pro': len(pro), 'aime': len(aime)}))


if __name__ == '__main__':
    main()
