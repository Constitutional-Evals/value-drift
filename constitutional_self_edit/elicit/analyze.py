"""Load results into a flat table and compute summary statistics."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recursive_oct.measurement import normalized_word_levenshtein  # noqa: E402

RUNS = ROOT / 'runs' / 'elicit'
MODELS = json.loads((ROOT / 'configs' / 'elicitation' / 'models.json').read_text())
AXES = ['autonomy_vs_protection', 'permissive_vs_cautious', 'corrigibility', 'honesty_strictness',
        'third_party_weight', 'ai_self_focus']


def load(batches, judge_file='judge.json'):
    rows = []
    for b in batches:
        for res in sorted((RUNS / b).glob('*/gen_*/result.json')):
            r = json.loads(res.read_text())
            d = res.parent
            before, after = (d / 'input.md').read_text(), (d / 'output.md').read_text()
            spec = r['arm_spec']
            row = {
                'batch': b, 'trial': d.parent.name, 'generation': int(d.name.split('_')[1]),
                'model': r['model'], 'arm': r['arm'], 'doc': d.parent.name.split('__')[2],
                'rep': int(d.parent.name.split('__r')[-1]),
                'deliberation': spec.get('deliberation'), 'framing': spec.get('framing', 'original' if spec.get('style') == 'original' else 'generations'),
                'thinking': spec.get('thinking', True), 'disclosure': spec.get('disclosure', 'none'),
                'stopping': spec.get('stopping', 'fixed'),
                'status': r['status'], 'failure': r['failure'], 'edited': r['status'] == 'EDITED',
                'failed': r['status'] == 'FAILURE', 'invalid_calls': r['invalid_calls'],
                'words_before': r['words_before'], 'words_after': r['words_after'],
                'distance': normalized_word_levenshtein(before, after) if r['status'] == 'EDITED' else 0.0,
                'cost': r['cost'], 'reasoning_tokens': r['reasoning_tokens'], 'api_calls': r['api_calls'],
                'decision_summary': r.get('decision_summary'), 'dir': str(d),
            }
            j = d / judge_file
            if j.exists():
                jd = json.loads(j.read_text())
                ch = jd.get('changes') or []
                row.update(subst=jd['substantiveness'], n_changes=len(ch),
                           n_subst_changes=sum(c.get('effect') == 'substantive' for c in ch),
                           headline=jd.get('headline'), topics=[c.get('topic') for c in ch if c.get('effect') == 'substantive'])
                for a in AXES:
                    row['ax_' + a] = (jd.get('axes') or {}).get(a, 0)
            elif r['status'] != 'EDITED':
                row.update(subst=0 if r['status'] == 'UNCHANGED' else np.nan, n_changes=0, n_subst_changes=0)
            rows.append(row)
    df = pd.DataFrame(rows)
    if len(df):
        df['label'] = df.model.map(lambda m: MODELS[m]['label'])
        df['open'] = df.model.map(lambda m: MODELS[m]['open'])
        df['family'] = df.model.map(lambda m: MODELS[m]['family'])
        # A review is "substantive" if the judge found behavior-changing content (score >= 2).
        df['substantive'] = (df.subst >= 2).astype(float).where(df.subst.notna())  # NaN if edited but unjudged
    return df


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan, np.nan)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return p, max(0, centre - half), min(1, centre + half)


def rate_table(df, by, col='edited'):
    g = df.groupby(by)
    out = g.agg(n=(col, 'size'), k=(col, 'sum'), failed=('failed', 'sum'),
                mean_subst=('subst', 'mean'), mean_dist=('distance', 'mean'),
                words_after=('words_after', 'mean'), cost=('cost', 'sum')).reset_index()
    ci = out.apply(lambda r: wilson(r.k, r.n), axis=1, result_type='expand')
    out[['rate', 'lo', 'hi']] = ci
    return out
