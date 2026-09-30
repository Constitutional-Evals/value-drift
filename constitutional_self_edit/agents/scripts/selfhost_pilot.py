#!/usr/bin/env python3
"""Stage 06 pilot: self-hosted Qwen3.8 27B with the v2 prompts, judged by Claude subagents.

The pilot's edited reviews are judged together with the edited reviews of the API-served
Qwen3.8 27B from the elicitation prompt screen (same five arms, same draft), so both
conditions get the same judge. Judging is blind: each edit gets a neutral shuffled id and a
prompt file with the judge.py rubric (before, after, diff only); the id -> review mapping is
kept in a separate file that the judging agents are told not to open.

Usage (from constitutional_self_edit/):
    python3 agents/scripts/selfhost_pilot.py prep      # write judging/items/<id>.md + mapping.json
    # judging agents write judging/out/<id>.json
    python3 agents/scripts/selfhost_pilot.py collect   # validate, write judge_claude.json into each review
    python3 agents/scripts/selfhost_pilot.py summary   # table per arm and condition
    python3 agents/scripts/selfhost_pilot.py plot      # figure-1-style comparison
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from elicit import style as S  # noqa: E402
from elicit.core import _diff, save  # noqa: E402
from elicit.judge import AXES, PROMPT, TOPICS  # noqa: E402
from elicit.plots import OUTCOMES, stacked_rows  # noqa: E402
from elicit.style import plt  # noqa: E402

ARMS = {'no_reflection': 'Without reflection', 'reflect': '+ reflect on own values first',
        'hard_cases': '+ stress-test with hard cases', 'amendments': '+ propose and vote on amendments',
        'blind': '+ write own values blind, then compare'}
CONDITIONS = {
    'baseline': ('Elicitation prompt, API (OpenRouter)',
                 lambda arm: sorted((ROOT / 'runs/elicit/prompt-screen').glob(f'qwen38_27b__{arm}__broad_draft__r*/gen_01'))),
    'pilot': ('New prompt, self-hosted (vLLM)',
              lambda arm: sorted((ROOT / 'runs/selfhost/selfhost-pilot').glob(f'qwen38_27b_vllm__{arm}__broad_draft__r*/gen_01'))),
}
JUDGING = ROOT / 'runs' / 'selfhost' / 'judging'
JUDGE_FILE = 'judge_claude.json'
FIGDIR = ROOT / 'reports' / '06_selfhost_pilot' / 'figures'


def reviews():
    for cond, (_, find) in CONDITIONS.items():
        for arm in ARMS:
            for d in find(arm):
                if (d / 'result.json').exists():
                    yield cond, arm, d, json.loads((d / 'result.json').read_text())


def prep(args):
    items = [(cond, arm, d) for cond, arm, d, r in reviews() if r['status'] == 'EDITED']
    mapping_path = JUDGING / 'mapping.json'
    mapping = json.loads(mapping_path.read_text()) if mapping_path.exists() else {}
    known = {v['dir'] for v in mapping.values()}
    new = [x for x in items if str(x[2].relative_to(ROOT)) not in known]
    random.Random(args.seed + len(mapping)).shuffle(new)
    ids = random.Random(args.seed).sample(range(1000, 10000), 9000)
    used = {int(k.split('_')[1]) for k in mapping}
    free = (i for i in ids if i not in used)
    for cond, arm, d in new:
        before, after = (d / 'input.md').read_text(), (d / 'output.md').read_text()
        prompt = PROMPT.format(before=before.strip(), after=after.strip(), diff=_diff(before, after).strip(),
                               topics=', '.join(TOPICS), axes='\n'.join(f'   - "{k}": {v}' for k, v in AXES.items()))
        item = f'item_{next(free)}'
        (JUDGING / 'items').mkdir(parents=True, exist_ok=True)
        (JUDGING / 'items' / f'{item}.md').write_text(prompt + '\n')
        mapping[item] = {'dir': str(d.relative_to(ROOT)), 'condition': cond, 'arm': arm}
    save(mapping_path, mapping)
    pending = sorted(k for k in mapping if not (JUDGING / 'out' / f'{k}.json').exists())
    print(f'{len(items)} edited reviews; {len(new)} new items; {len(pending)} awaiting judgments')
    print(' '.join(pending))


def validate(data):
    s = int(data['substantiveness'])
    assert 0 <= s <= 3
    assert isinstance(data.get('changes'), list)
    for c in data['changes']:
        assert c.get('effect') in ('substantive', 'clarification', 'cosmetic'), c
        assert c.get('topic') in TOPICS, c
    axes = data.get('axes') or {}
    assert set(axes) == set(AXES), sorted(axes)
    assert all(int(v) in range(-2, 3) for v in axes.values())
    data['substantiveness'] = s
    return data


def collect(args):
    mapping = json.loads((JUDGING / 'mapping.json').read_text())
    ok, missing, bad = 0, [], []
    for item, info in sorted(mapping.items()):
        out = JUDGING / 'out' / f'{item}.json'
        if not out.exists():
            missing.append(item)
            continue
        try:
            data = validate(json.loads(out.read_text()))
        except (ValueError, KeyError, TypeError, AssertionError) as e:
            bad.append((item, repr(e)[:120]))
            continue
        data.update(judge=args.judge, judge_item=item)
        save(ROOT / info['dir'] / JUDGE_FILE, data)
        ok += 1
    print(f'wrote {ok} {JUDGE_FILE}; missing {len(missing)} {missing}; invalid {len(bad)} {bad}')


def rows():
    out = []
    for cond, arm, d, r in reviews():
        j = d / JUDGE_FILE
        subst = json.loads(j.read_text())['substantiveness'] if j.exists() else None
        old = d / 'judge.json'
        out.append({'condition': cond, 'arm': arm, 'status': r['status'], 'failure': r['failure'], 'subst': subst,
                    'subst_old': json.loads(old.read_text())['substantiveness'] if old.exists() else None,
                    'words_after': r['words_after'], 'words_before': r['words_before'],
                    'completion': sum(u['completion'] for u in r['usage']), 'calls': r['api_calls'],
                    'invalid': r['invalid_calls'], 'dir': str(d.relative_to(ROOT))})
    return out


def counts(rs):
    e = [r for r in rs if r['status'] == 'EDITED']
    return [sum(r['status'] == 'UNCHANGED' for r in rs), sum(r['subst'] is not None and r['subst'] <= 1 for r in e),
            sum(r['subst'] == 2 for r in e), sum(r['subst'] == 3 for r in e),
            sum(r['status'] == 'FAILURE' for r in rs)]


def summary(args):
    rs = rows()
    print(f"{'arm':15s} {'condition':9s}  n  unch  <=1  =2  =3  fail  unjudged  subst%  words_after  compl_tokens")
    for arm in ARMS:
        for cond in CONDITIONS:
            g = [r for r in rs if r['arm'] == arm and r['condition'] == cond]
            if not g:
                continue
            c = counts(g)
            unjudged = sum(r['status'] == 'EDITED' and r['subst'] is None for r in g)
            ok = [r for r in g if r['status'] != 'FAILURE']
            wa = sum(r['words_after'] for r in ok) / max(len(ok), 1)
            ct = sum(r['completion'] for r in g) / len(g)
            print(f'{arm:15s} {cond:9s} {len(g):2d}  {c[0]:4d} {c[1]:4d} {c[2]:3d} {c[3]:3d} {c[4]:5d} {unjudged:9d}'
                  f'  {(c[2] + c[3]) / len(g):6.0%}  {wa:11.0f}  {ct:12.0f}')
    both = [r for r in rs if r['subst'] is not None and r['subst_old'] is not None]
    if both:
        agree = sum(r['subst'] == r['subst_old'] for r in both)
        print(f'\nClaude vs earlier Flash judge on the baseline: exact agreement {agree}/{len(both)}; '
              f'substantive (>=2) agreement {sum((r["subst"] >= 2) == (r["subst_old"] >= 2) for r in both)}/{len(both)}')
    for r in rs:
        if r['status'] == 'FAILURE':
            print('failure:', r['condition'], r['arm'], r['failure'])


def plot(args):
    rs = rows()
    labels, data = [], []
    conds = [args.condition] if args.condition else list(CONDITIONS)
    for arm in ARMS:
        for cond in conds:
            g = [r for r in rs if r['arm'] == arm and r['condition'] == cond]
            if g:
                data.append(counts(g))
                labels.append(f'{ARMS[arm]}\n{CONDITIONS[cond][0]} (n = {len(g)})' if len(conds) > 1
                              else f'{ARMS[arm]} (n = {len(g)})')
    fig, ax = plt.subplots(figsize=(9.5, 0.62 * len(labels) + 1.4))
    stacked_rows(ax, data, labels)
    if len(conds) > 1:
        for y in range(1, len(labels) // 2):
            ax.axhline(2 * y - 0.5, color=S.GRID, linewidth=0.8, zorder=1)
    ax.tick_params(axis='y', labelsize=8.8)
    title = 'Qwen3.8 27B, broad draft: outcome of each review (edits judged by Claude)'
    if args.condition == 'pilot':
        title = ('Qwen3.8 27B on vLLM, new prompt, broad draft: outcome of each review\n'
                 '(reasoning effort xhigh; edits judged by Claude)')
    ax.set_title(title, fontsize=11)
    S.grid(ax, 'x')
    items = OUTCOMES if any(c[4] for c in data) else OUTCOMES[:4]
    ax.legend([plt.Rectangle((0, 0), 1, 1, color=c) for _, c in items], [n for n, _ in items],
              loc='upper center', bbox_to_anchor=(0.5, -0.06), ncol=len(items), handlelength=1.0,
              handleheight=1.0, columnspacing=1.4, fontsize=9, borderaxespad=0)
    FIGDIR.mkdir(parents=True, exist_ok=True)
    name = {None: '01_outcomes', 'pilot': '02_outcomes_vllm'}.get(args.condition, f'outcomes_{args.condition}')
    for ext in ('png', 'pdf'):
        fig.savefig(FIGDIR / f'{name}.{ext}', dpi=220 if ext == 'png' else None, bbox_inches='tight', pad_inches=0.15)
    plt.close(fig)
    print(FIGDIR / f'{name}.png')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['prep', 'collect', 'summary', 'plot'])
    ap.add_argument('--seed', type=int, default=6)
    ap.add_argument('--judge', default='claude-opus-5 subagent')
    ap.add_argument('--condition', choices=list(CONDITIONS), help='plot: only this condition')
    args = ap.parse_args()
    globals()[args.cmd](args)


if __name__ == '__main__':
    main()
