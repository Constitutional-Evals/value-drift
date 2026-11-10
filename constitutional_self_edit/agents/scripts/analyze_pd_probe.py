#!/usr/bin/env python3
"""Pilot checks for the PD cooperation probe (probe_pd_cooperation.py). Offline: reads runs/pd_probe/<label>/.

Per model: the score s (share of COOPERATE against the fixed panel) per document; its repeat-sample
reliability (odd vs even samples, Spearman-Brown corrected) and binomial SE; how documents spread over
(cooperation vs C_cooperate, cooperation vs C_defect); and whether the probe predicts the recorded move,
both against the recorded partner and from the panel score alone.

Usage (from constitutional_self_edit):
  python3 agents/scripts/analyze_pd_probe.py [pilot]

Knowledge graph notes (SPAR/): PD Cooperation Probe.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
PANEL = ('cooperate', 'defect', 'conditional')


def pearson(x, y):
    mx, my = mean(x), mean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sx, sy = sum((a - mx) ** 2 for a in x) ** .5, sum((b - my) ** 2 for b in y) ** .5
    return sxy / (sx * sy) if sx and sy else float('nan')


def auc(pos, neg):
    """P(score of a random positive > a random negative), ties half."""
    if not pos or not neg:
        return float('nan')
    return mean((p > n) + .5 * (p == n) for p in pos for n in neg)


def main():
    out = ROOT / 'runs' / 'pd_probe' / (sys.argv[1] if len(sys.argv) > 1 else 'pilot')
    docs = {(d['model'], d['key']): d for d in json.loads((out / 'documents.json').read_text())}
    res = json.loads((out / 'results.json').read_text())
    acts = defaultdict(list)  # (model, key, partner) -> [(sample, 1/0)]
    missing = 0
    for r in res:
        if r['action'] in ('C', 'D'):
            acts[(r['model'], r['key'], r['partner'])].append((r['sample'], r['action'] == 'C'))
        else:
            missing += 1
    print(f"{len(res)} calls, {missing} without an action, ${sum(r['cost'] for r in res):.2f}\n")

    for model in sorted({m for m, _ in docs}):
        keys = [k for m, k in docs if m == model]
        rate = {(k, p): mean(v for _, v in acts[(model, k, p)]) for k in keys
                for p in (*PANEL, 'recorded') if acts[(model, k, p)]}
        s = {k: mean(rate[(k, p)] for p in PANEL if (k, p) in rate) for k in keys}
        half = {h: {k: mean(v for p in PANEL for i, v in acts[(model, k, p)] if i % 2 == h) for k in keys}
                for h in (0, 1)}
        r = pearson([half[0][k] for k in keys], [half[1][k] for k in keys])
        n = mean(sum(len(acts[(model, k, p)]) for p in PANEL) for k in keys)
        se = mean((s[k] * (1 - s[k]) / n) ** .5 for k in keys)
        print(f'== {model}: {len(keys)} documents, ~{n:.0f} panel samples each')
        print(f'  s: mean {mean(s.values()):.2f}, split-half r {r:.2f} (Spearman-Brown {2 * r / (1 + r):.2f}), '
              f'mean binomial SE {se:.3f}')
        for p in PANEL:
            print(f'  vs {p:<11} mean P(C) {mean(rate[(k, p)] for k in keys if (k, p) in rate):.2f}')
        grid = defaultdict(int)
        for k in keys:
            grid[(round(rate.get((k, 'cooperate'), 0)), round(rate.get((k, 'defect'), 0)))] += 1
        print('  documents by (C vs cooperate, C vs defect), rounded:',
              {f'({a},{b})': c for (a, b), c in sorted(grid.items())})
        rec = [(rate[(k, 'recorded')], s[k], docs[(model, k)]['recorded']['action']) for k in keys
               if (k, 'recorded') in rate and docs[(model, k)].get('recorded')]
        if rec:
            hit = mean((p >= .5) == (a == 'C') for p, _, a in rec)
            print(f'  recorded move vs probe against the same partner: majority agrees {hit:.0%} of {len(rec)}; '
                  f'AUC {auc([p for p, _, a in rec if a == "C"], [p for p, _, a in rec if a == "D"]):.2f}; '
                  f'panel-s AUC {auc([q for _, q, a in rec if a == "C"], [q for _, q, a in rec if a == "D"]):.2f}')
        print('  lowest/highest s:')
        for k in sorted(keys, key=s.get)[:3] + sorted(keys, key=s.get)[-3:]:
            text = ' '.join(docs[(model, k)]['text'].split())
            print(f'    {s[k]:.2f}  ' + ' '.join(f'{p[:4]}={rate.get((k, p), float("nan")):.1f}'
                                             for p in (*PANEL, 'recorded')) + f'  {text[:90]}')
        print()


if __name__ == '__main__':
    main()
