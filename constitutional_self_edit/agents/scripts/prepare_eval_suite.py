#!/usr/bin/env python3
"""Build the checkpoint evaluation suite in data/eval_suite/ from pinned public datasets.

- mmlu.jsonl: 10 test questions per subject (57 subjects, 570), capability.
- gsm8k.jsonl: 200 test problems, capability with reasoning (answers checked exactly).
- sycophancy.jsonl: 200 of the MMLU questions with a wrong answer to push back with.
- ai_risk.jsonl: Anthropic's human-written advanced-AI-risk questions (two or more options, one
  "matching behavior") for corrigibility, survival instinct, power seeking, and coordination with other
  AIs. The matching answer is the safe one in the first three files and the risky one in the last.
- litmus.jsonl: LitmusValues' 3,000 AIRiskDilemmas (Chiu et al., 2025), one row per dilemma with both
  actions, each action's value classes (from the dataset's value map) and risky-behavior tags (from its
  full release). 300 are marked for the run with thinking on.
Licenses: MMLU and GSM8K MIT, model-written-evals and AIRiskDilemmas CC-BY-4.0.

Usage (from constitutional_self_edit/, needs pyarrow): python3 agents/scripts/prepare_eval_suite.py
"""
import io
import json
import random
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / 'data' / 'eval_suite'
SOURCES = {
    'mmlu': ('cais/mmlu', 'c30699e8356da336a370243923dbaf21066bb9fe', 'all/test-00000-of-00001.parquet'),
    'gsm8k': ('openai/gsm8k', '740312add88f781978c0658806c59bc2815b9866', 'main/test-00000-of-00001.parquet'),
    'ai_risk': ('Anthropic/model-written-evals', 'd533f626cc321c92175a58ee570aa3cdb87238d1',
                'advanced-ai-risk/human_generated_evals/{}.jsonl'),
    'litmus': ('kellycyy/AIRiskDilemmas', '8674d1f5844c3909b05e06d9f30bbc2b7c753f39', '{}.jsonl'),
}
AI_RISK = ('corrigible-neutral-HHH', 'survival-instinct', 'power-seeking-inclination', 'coordinate-other-ais')
SEED = 20260928
LITMUS_THINK_SUBSET = 300


def fetch(repo, revision, path):
    url = f'https://huggingface.co/datasets/{repo}/resolve/{revision}/{path}'
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def parquet_rows(data):
    import pyarrow.parquet as pq
    return pq.read_table(io.BytesIO(data)).to_pylist()


def jsonl(data):
    return [json.loads(line) for line in data.decode().splitlines() if line.strip()]


def litmus_dilemmas(repo, revision, template):
    """Pair the dataset's two rows per dilemma (Action 1, Action 2) and attach value classes and risk tags."""
    rows = jsonl(fetch(repo, revision, template.format('model_eval')))
    value_class = {r['value']: r['value_class'] for r in jsonl(fetch(repo, revision, template.format('value_map')))}
    tags = {(r['dilemma'], r['action']): r for r in jsonl(fetch(repo, revision, template.format('full')))}
    dilemmas = []
    for k in range(0, len(rows), 2):
        pair = rows[k:k + 2]
        assert pair[0]['dilemma'] == pair[1]['dilemma'] and [a['action'].split(':')[0] for a in pair] == ['Action 1', 'Action 2']
        full = [tags.get((a['dilemma'], a['action'])) for a in pair]
        dilemmas.append({'id': f'litmus-{k // 2:04d}', 'dilemma': pair[0]['dilemma'],
                         'context': next((f['context'] for f in full if f), None), 'think_subset': False,
                         'actions': [{'action': a['action'], 'values': a['values'],
                                      'value_classes': [value_class[v] for v in a['values']], 'targets': a['targets'],
                                      'risky_behaviors': f['risky_behaviors'] if f else None} for a, f in zip(pair, full)]})
    return dilemmas


def write(name, rows):
    (OUT / f'{name}.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    return len(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    counts = {}
    repo, revision, path = SOURCES['mmlu']
    mmlu = parquet_rows(fetch(repo, revision, path))
    by_subject = {}
    for i, row in enumerate(mmlu):
        by_subject.setdefault(row['subject'], []).append({'id': f'mmlu-{i:05d}', 'subject': row['subject'],
            'question': row['question'], 'choices': list(row['choices']), 'answer': 'ABCD'[row['answer']]})
    sample = [r for subject in sorted(by_subject) for r in rng.sample(by_subject[subject], 10)]
    counts['mmlu'] = write('mmlu', sample)
    syco = rng.sample(sample, 200)
    counts['sycophancy'] = write('sycophancy', [{**r, 'id': r['id'].replace('mmlu', 'syco'),
        'pushback': rng.choice([c for c in 'ABCD' if c != r['answer']])} for r in syco])
    repo, revision, path = SOURCES['gsm8k']
    gsm = parquet_rows(fetch(repo, revision, path))
    picks = rng.sample(range(len(gsm)), 200)
    counts['gsm8k'] = write('gsm8k', [{'id': f'gsm8k-{i:04d}', 'question': gsm[i]['question'],
        'answer': gsm[i]['answer'].split('####')[-1].strip().replace(',', '')} for i in sorted(picks)])
    repo, revision, template = SOURCES['ai_risk']
    risk = []
    for name in AI_RISK:
        for j, line in enumerate(fetch(repo, revision, template.format(name)).decode().splitlines()):
            if line.strip():
                row = json.loads(line)
                risk.append({'id': f'{name}-{j:03d}', 'category': name, 'question': row['question'],
                             'matching': row['answer_matching_behavior'].strip(),
                             'not_matching': row['answer_not_matching_behavior'].strip()})
    counts['ai_risk'] = write('ai_risk', risk)
    dilemmas = litmus_dilemmas(*SOURCES['litmus'])
    for i in rng.sample(range(len(dilemmas)), LITMUS_THINK_SUBSET):
        dilemmas[i]['think_subset'] = True
    counts['litmus'] = write('litmus', dilemmas)
    manifest = {'seed': SEED, 'sources': {k: {'repo': v[0], 'revision': v[1]} for k, v in SOURCES.items()},
                'ai_risk_files': AI_RISK, 'counts': counts}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
