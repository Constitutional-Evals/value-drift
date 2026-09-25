#!/usr/bin/env python3
"""Recompute every number cited in reports/05_elicitation/ELICIT_REPORT.md from saved results.

Usage (from constitutional_self_edit/): python3 agents/scripts/elicit_report_numbers.py
"""
import itertools
import json
import sys
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings('ignore')
from elicit.analyze import AXES, MODELS, load  # noqa: E402
from elicit.plots import CAP, chain_frame, convergence_table  # noqa: E402

SINGLE = ['prompt-screen', 'framing-variants', 'thinking-off', 'long-constitution', 'cross-model', 'cross-model-premium', 'cross-model-thinking-off']
CHAINS = ['chains-uncapped', 'chains-capped', 'chains-glm53-uncapped', 'chains-gpt6-sol']


def frac(s):
    s = s.dropna()
    return f'{int(s.sum())}/{len(s)}'


single = load(SINGLE)
chains = load(CHAINS)
print(f'reviews: single={len(single)} chains={len(chains)} total={len(single) + len(chains)}; '
      f'failed={int(single.failed.sum() + chains.failed.sum())} '
      f'({single[single.failed].model.value_counts().to_dict()})')
allr = load(SINGLE + CHAINS)
inv = allr[allr.invalid_calls > 0]
print(f'invalid-call reviews={len(inv)} recovered={int((~inv.failed).sum())}')

# ---- cross-model (blind / no_reflection on the 227-word draft)
cm = load(['prompt-screen', 'cross-model', 'cross-model-premium'])
cm = cm[cm.arm.isin(['blind', 'no_reflection']) & ~cm.failed]
b, d = cm[cm.arm == 'blind'], cm[cm.arm == 'no_reflection']
print(f'\nblind: substantive {frac(b.substantive)} = {b.substantive.mean():.0%}; models={b.model.nunique()}')
per = b.groupby('model').substantive.agg(['sum', 'size'])
print('models substantive every time:', int((per['sum'] == per['size']).sum()), 'of', len(per))
print('models below:', {MODELS[m]['label']: f"{int(r['sum'])}/{int(r['size'])}" for m, r in per.iterrows() if r['sum'] < r['size']})
pd_ = d.groupby('model').edited.agg(['sum', 'size'])
print('no_reflection: models editing >= all-but-one:', int(((pd_['sum'] >= pd_['size'] - 1)).sum()), 'of', len(pd_),
      '| never:', [MODELS[m]['label'] for m, r in pd_.iterrows() if r['sum'] == 0])
print('no_reflection per model:', {MODELS[m]['label']: f"{int(r['sum'])}/{int(r['size'])}" for m, r in pd_.iterrows()})

rows = []
for m, g in cm.groupby('model'):
    bb, dd = g[g.arm == 'blind'], g[g.arm == 'no_reflection']
    rows.append(dict(m=m, cap=CAP.get(m), open=MODELS[m]['open'], no_reflection=dd.edited.mean(),
                     nsub=bb.n_subst_changes.mean(), words=(bb.words_after - bb.words_before).mean()))
import pandas as pd  # noqa: E402
P = pd.DataFrame(rows)
for col in ('no_reflection', 'nsub', 'words'):
    r = stats.spearmanr(P.cap, P[col])
    print(f'spearman cap vs {col}: rho={r.statistic:.2f} p={r.pvalue:.3g}')
print('open vs closed Mann-Whitney no_reflection p=%.2f' % stats.mannwhitneyu(P[P.open].no_reflection, P[~P.open].no_reflection).pvalue,
      '| words added open=%.0f closed=%.0f' % (P[P.open].words.mean(), P[~P.open].words.mean()))
print('nsub per model:', {MODELS[r.m]['label']: round(r.nsub, 1) for r in P.sort_values('nsub').itertuples()})
print('words added per model (closed):', {MODELS[r.m]['label']: round(r.words) for r in P[~P.open].itertuples()})

e = b[b.edited & b.subst.notna()]
kinds = Counter()
topics = Counter()
for r in e.itertuples():
    for c in json.loads((Path(r.dir) / 'judge.json').read_text())['changes']:
        kinds[c.get('kind')] += 1
    topics.update(r.topics or [])
print(f'\nblind edits={len(e)} changes={sum(kinds.values())} kinds={dict(kinds)}')
print('net-shrink edits:', int((e.words_after < e.words_before).sum()), '| median words added:',
      float((e.words_after - e.words_before).median()))
print('top topics:', topics.most_common(8))
print('oversight axis mean: closed=%.2f open=%.2f | share reducing: closed=%.0f%% open=%.0f%%' % (
    e[~e.open].ax_corrigibility.mean(), e[e.open].ax_corrigibility.mean(),
    100 * (e[~e.open].ax_corrigibility < 0).mean(), 100 * (e[e.open].ax_corrigibility < 0).mean()))

# ---- thinking off vs on (blind)
off = load(['thinking-off', 'cross-model-thinking-off'])
off = off[(off.arm == 'blind_thinking_off') & ~off.failed]
print('\nthinking off vs on (blind, substantive):')
for m, g in off.groupby('model'):
    on = b[b.model == m]
    print(f'  {MODELS[m]["label"]:20s} off {frac(g.substantive)}  on {frac(on.substantive)}')

# ---- chains
ch, rat, emb = chain_frame()
ch = ch[~ch.failed]
print(f'\nchain reviews={len(ch)}')
print('unchanged per model (all conditions):', ch.groupby('model').apply(
    lambda x: f"{int((x.status == 'UNCHANGED').sum())}/{len(x)}").to_dict())
print('substantive at gen 6:', ch[ch.generation == 6].groupby(['model', 'capped']).substantive.mean().round(2).to_dict())
print('words at gen 6 (uncapped mean/max):', ch[(ch.generation == 6) & ~ch.capped].groupby('model').words_after.agg(['mean', 'max']).round(0).to_dict())
k = Counter()
for r in ch[ch.edited].itertuples():
    for c in json.loads((Path(r.dir) / 'judge.json').read_text())['changes']:
        k[(r.capped, c.get('kind'))] += 1
for cap in (False, True):
    tot = sum(v for (c, _), v in k.items() if c == cap)
    print(f'capped={cap}: changes={tot} remove={k[(cap, "remove")]} ({k[(cap, "remove")] / tot:.1%}) '
          f'modify={k[(cap, "modify")] / tot:.0%}')
print('capped substantive rate:', ch[ch.capped].groupby('model').substantive.mean().round(2).to_dict())

AX = ['oversight_deference', 'user_autonomy', 'caution', 'honesty_strictness', 'third_party_concern', 'ai_agency']
out = []
for (m, cap), g in ch.groupby(['model', 'capped']):
    ends = {}
    for t, c in g.groupby('trial'):
        c = c.sort_values('generation')
        if c.generation.max() == 6 and c.h_in.iloc[0] in rat and c.h_out.iloc[-1] in rat:
            ends[t] = (c.doc.iloc[0], np.array([rat[c.h_in.iloc[0]][a] for a in AX]),
                       np.array([rat[c.h_out.iloc[-1]][a] for a in AX]))
    b0, b6, w6 = [], [], []
    for x, y in itertools.combinations(ends, 2):
        (sx, x0, x6), (sy, y0, y6) = ends[x], ends[y]
        (b6 if sx != sy else w6).append(np.abs(x6 - y6).mean())
        if sx != sy:
            b0.append(np.abs(x0 - y0).mean())
    mean_end = {a: np.mean([v[2][i] for v in ends.values()]) for i, a in enumerate(AX)}
    out.append(dict(model=MODELS[m]['label'], capped=cap, n=len(ends), spread0=np.mean(b0), spread6=np.mean(b6),
                    within6=np.mean(w6) if w6 else np.nan, oversight=mean_end['oversight_deference'],
                    agency=mean_end['ai_agency'], caution=mean_end['caution']))
print(pd.DataFrame(out).round(2).to_string())
t = convergence_table()
t = t[t.generation == 6].round(3)
print(t[['model', 'capped', 'between', 'within', 'n']].to_string())
