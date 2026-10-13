#!/usr/bin/env python3
"""Report page for the work after round 1 of the recursive OCT loop, built only from the result files.

Covers: SFT run for 2 and 3 epochs, the model spec midtraining pilot (27B, with the corrected AFT, and the
Qwen3.5-9B-Base arm), how the trained models revise C_001 (single reviews, replicate reviews, and edit sizes
against the inference-only chains), and the pilot of writing the constitution from scratch. Same style as
the round 1 page (build_round_report.py). LIMA prompts are never shown.

Usage (from constitutional_self_edit/):
    python3 agents/scripts/build_followups_report.py --out reports/round1_followups/report.html
"""
import argparse
import csv
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_oct_demo_page import AXIS_NAMES, diff_html  # noqa: E402
from build_round_report import HEAD, e, pct, table  # noqa: E402
from edit_sizes import TRAINED, measure  # noqa: E402
from selfhost_v3 import RATE_AXES  # noqa: E402

RUN2 = ROOT / 'runs/oct-loop/oct-qwen38-27b-broad-run2'
EVAL = ROOT / 'runs/oct-loop/eval'
MSM = ROOT / 'runs/msm-loop/eval/pilot'
PILOT = ROOT / 'runs/self-draft/pilot'
RISK = {'Declines power': 'power-seeking-inclination', 'Accepts shutdown': 'survival-instinct',
        'Accepts a goal change': 'corrigible-neutral-HHH', 'Refuses to collude with other AIs': 'coordinate-other-ais'}


def load(path):
    return json.loads(Path(path).read_text())


def num(x, digits=1, unit=''):
    return '–' if x is None else f'<span class="num">{x:,.{digits}f}{unit}</span>'


def summaries():
    """Each model's own metrics.json (an evaluation folder's summary.json holds only its last invocation's
    models), with the labeled LitmusValues results merged in for run 2's models."""
    files = {n: EVAL / f'round_001_run2/{n}/metrics.json' for n in ('base', 'dpo', 'sft')}
    files.update({n: EVAL / f'round_001_run2_sft_epochs/{n}/metrics.json' for n in ('sft_e2', 'sft_e3')})
    files.update({n: MSM / f'{n}/metrics.json' for n in ('msm', 'aft')})
    files['aft_fixed'] = MSM / 'aft_fixed/aft_fixed/metrics.json'
    files.update({f'9b_{n}': MSM / f'qwen35-9b-base/{n}/metrics.json' for n in ('msm_aft', 'aft_only')})
    s = {n: load(f) for n, f in files.items()}
    for n in ('base', 'dpo', 'sft'):
        s[n].update(load(EVAL / f'round_001_run2_litmus_v2/{n}/metrics.json'))
    return s


def kl_from_base():
    """KL(model || base) per token on each model's own answers."""
    get = lambda path, row: float(re.search(rf'^\| {re.escape(row)} \| \S+ \| ([\d.]+)', Path(path).read_text(), re.M)[1])
    kl = {'dpo': get(EVAL / 'round_001_run2/kl/summary.md', 'KL(after DPO || base)'),
          'sft': get(EVAL / 'round_001_run2/kl/summary.md', 'KL(after SFT || base)'),
          'sft_e2': get(EVAL / 'round_001_run2_sft_epochs/kl_e2/summary.md', 'KL(after SFT || base)'),
          'sft_e3': get(EVAL / 'round_001_run2_sft_epochs/kl_e3/summary.md', 'KL(after SFT || base)'),
          'msm': get(MSM / 'kl/summary.md', 'KL(after DPO || base)'),
          'aft': get(MSM / 'kl/summary.md', 'KL(after SFT || base)'),
          'aft_fixed': get(MSM / 'aft_fixed/kl/summary.md', 'KL(aft_fixed || base)')}
    sft_dpo = {'sft': get(EVAL / 'round_001_run2/kl/summary.md', 'KL(after SFT || after DPO)'),
               'sft_e2': get(EVAL / 'round_001_run2_sft_epochs/kl_e2/summary.md', 'KL(after SFT || after DPO)'),
               'sft_e3': get(EVAL / 'round_001_run2_sft_epochs/kl_e3/summary.md', 'KL(after SFT || after DPO)')}
    nine = get(MSM / 'qwen35-9b-base/kl/summary.md', 'KL(msm_aft || base)')
    return kl, sft_dpo, nine


def eval_rows(s, names, kl, extra=()):
    g = lambda n, *keys: _dig(s.get(n, {}), keys)
    rows = [['MMLU', *[pct(g(n, 'mmlu', 'accuracy')) for n in names]],
            ['GSM8K, reasoning on', *[pct(g(n, 'gsm8k', 'accuracy')) for n in names]],
            ['GSM8K reasoning tokens', *[num(g(n, 'gsm8k', 'thinking_tokens'), 0) for n in names]],
            ['Sycophancy: drops a correct answer under pushback', *[pct(g(n, 'sycophancy', 'switched_to_pushback')) for n in names]]]
    rows += [[label, *[pct(g(n, 'ai_risk', key, 'safe_answer')) for n in names]] for label, key in RISK.items()]
    rows += [['LitmusValues: picks the risky action, reasoning off', *[pct(g(n, 'litmus_labeled', 'chose_risky_action', 'any', 'rate')) for n in names]],
             ['LitmusValues: picks the risky action, reasoning on', *[pct(g(n, 'litmus_labeled_think', 'chose_risky_action', 'any', 'rate')) for n in names]],
             ['Self-talk: tokens per turn (copy B)', *[num(g(n, 'selftalk', 'B', 'tokens'), 0) for n in names]],
             ['KL from the base model (nats per token)', *[num(kl.get(n), 3) if n != 'base' else num(0, 3) for n in names]]]
    return [r for r in rows] + list(extra)


def _dig(d, keys):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def markdown(text):
    """Enough Markdown for the drafted constitutions: headings, lists, bold, paragraphs."""
    out, para, items = [], [], []
    inline = lambda t: re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', e(t))
    def flush():
        if para:
            out.append(f'<p>{inline(" ".join(para))}</p>'); para.clear()
        if items:
            out.append('<ul>' + ''.join(f'<li>{inline(i)}</li>' for i in items) + '</ul>'); items.clear()
    for line in text.splitlines():
        heading = re.match(r'^(#{1,6})\s+(.*)', line)
        bullet = re.match(r'^\s*(?:[-*]|\d+\.)\s+(.*)', line)
        if heading:
            flush(); level = min(len(heading[1]) + 2, 6)
            out.append(f'<h{level}>{inline(heading[2])}</h{level}>')
        elif bullet:
            if para:
                flush()
            items.append(bullet[1])
        elif not line.strip():
            flush()
        else:
            if items:
                flush()
            para.append(line.strip())
    flush()
    return ''.join(out)


def line_svg(series, xlabels, ymax, label, fmt='{:.2f}', ref=None, height=220):
    """Lines over a shared x axis. series: [(name, values, css color var, dashed)]; values may hold None."""
    w, h, l, r, t, b = 560, height, 46, 84, 34, 28
    x = lambda i: l + (w - l - r) * i / max(1, len(xlabels) - 1)
    y = lambda v: t + (h - t - b) * (1 - v / ymax)
    ticks = [ymax * k / 4 for k in range(5)]
    out = [f'<line x1="{l}" x2="{w - r}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
           f'<text x="{l - 6}" y="{y(v) + 4:.1f}" text-anchor="end" class="tick">{fmt.format(v)}</text>' for v in ticks]
    out += [f'<text x="{x(i):.1f}" y="{h - 8}" text-anchor="middle" class="tick">{e(str(xl))}</text>' for i, xl in enumerate(xlabels)]
    if ref:
        value, text = ref
        out.append(f'<line x1="{l}" x2="{w - r}" y1="{y(value):.1f}" y2="{y(value):.1f}" stroke="var(--muted)" stroke-dasharray="2 4" stroke-width="1.5"/>'
                   f'<text x="{w - r + 6}" y="{y(value) + 4:.1f}" class="tick">{e(text)}</text>')
    for name, values, color, dashed in series:
        pts = [(x(i), y(v)) for i, v in enumerate(values) if v is not None]
        dash = ' stroke-dasharray="6 4"' if dashed else ''
        out.append(f'<polyline points="{" ".join(f"{a:.1f},{c:.1f}" for a, c in pts)}" fill="none" stroke="var({color})" stroke-width="2.2"{dash}/>')
        out += [f'<circle cx="{a:.1f}" cy="{c:.1f}" r="3.5" fill="var({color})"/>' for a, c in pts]
    # Legend across the top: a short line in each series' style, then its name.
    lx = l
    for name, values, color, dashed in series:
        dash = ' stroke-dasharray="6 4"' if dashed else ''
        out.append(f'<line x1="{lx}" x2="{lx + 22}" y1="12" y2="12" stroke="var({color})" stroke-width="2.2"{dash}/>'
                   f'<text x="{lx + 28}" y="16" class="series" fill="var(--ink)">{e(name)}</text>')
        lx += 28 + 7.2 * len(name) + 22
    return (f'<figure class="chart"><svg viewBox="0 0 {w} {h}" role="img" aria-label="{e(label)}">{"".join(out)}</svg>'
            f'<figcaption>{e(label)}</figcaption></figure>')


def strip_svg(groups, xmax, label, unit='%'):
    """Dots on a horizontal scale, one row per group. groups: [(name, values, css color var)]."""
    w, row, l, r, t = 560, 34, 190, 20, 10
    h = t + row * len(groups) + 26
    x = lambda v: l + (w - l - r) * v / xmax
    out = []
    for k in range(5):
        v = xmax * k / 4
        out.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{t}" y2="{h - 22}" class="grid"/>'
                   f'<text x="{x(v):.1f}" y="{h - 6}" text-anchor="middle" class="tick">{v:.0f}{unit}</text>')
    for i, (name, values, color) in enumerate(groups):
        cy = t + row * i + row / 2
        out.append(f'<text x="{l - 10}" y="{cy + 4:.1f}" text-anchor="end" class="tick label-tick">{e(name)}</text>')
        out += [f'<circle cx="{x(v):.1f}" cy="{cy:.1f}" r="5" fill="var({color})" fill-opacity=".75" stroke="var(--surface)" stroke-width="1.5"/>'
                for v in values]
        if len(values) > 1:
            m = statistics.mean(values)
            out.append(f'<line x1="{x(m):.1f}" x2="{x(m):.1f}" y1="{cy - 11:.1f}" y2="{cy + 11:.1f}" stroke="var(--ink)" stroke-width="2"/>')
    return (f'<figure class="chart"><svg viewBox="0 0 {w} {h}" role="img" aria-label="{e(label)}">{"".join(out)}</svg>'
            f'<figcaption>{e(label)}</figcaption></figure>')


def build():
    s, (kl, sft_dpo, kl9) = summaries(), kl_from_base()
    c001 = (RUN2 / 'C_001.md').read_text()
    perp = load(MSM / 'perplexity.json')
    perp.update(load(MSM / 'aft_fixed/perplexity.json'))
    perp9 = load(MSM / 'qwen35-9b-base/perplexity.json')
    epochs = list(csv.DictReader(open(ROOT / 'reports/09_oct_loop/figures/sft_epochs.csv')))
    loss = {e_: load(EVAL / f'round_001_run2_sft_epochs/train_{e_}/training_complete.json')['mean_loss'] for e_ in ('e2', 'e3')}
    loss['e1'] = load(RUN2 / 'round_001/final/training_complete.json')['mean_loss']

    # 1. SFT epochs.
    ep_names = ['base', 'dpo', 'sft', 'sft_e2', 'sft_e3']
    ep_head = ['', 'Base', 'After DPO', 'SFT, 1 epoch', 'SFT, 2 epochs', 'SFT, 3 epochs']
    ep_table = table(ep_head, eval_rows(s, ep_names, kl, extra=[
        ['KL of SFT from the DPO model', '–', '–', *[num(sft_dpo[n], 3) for n in ('sft', 'sft_e2', 'sft_e3')]],
        ['SFT training loss (mean over the epoch)', '–', '–', *[num(loss[k], 3) for k in ('e1', 'e2', 'e3')]]]))

    # 2. MSM.
    m_names = ['base', 'sft', 'msm', 'aft_fixed']
    m_head = ['', 'Base', 'OCT (DPO + SFT)', 'MSM: midtraining only', 'MSM + AFT']
    loss_row = lambda doc: ['Loss on the text of ' + doc + ' (nats per token)', num(perp['base'][doc]['nll_per_token'], 2), '–',
                            *[num(perp[n][doc]['nll_per_token'], 2) for n in ('msm', 'aft_fixed')]]
    msm_table = table(m_head, eval_rows(s, m_names, kl, extra=[
        loss_row('C_001'), loss_row('C_000'),
        ['Loss on an unrelated control text', num(perp['base']['control']['nll_per_token'], 2), '–',
         *[num(perp[n]['control']['nll_per_token'], 2) for n in ('msm', 'aft_fixed')]]]))
    g9 = lambda n, *k: _dig(s[f'9b_{n}'], k)
    nine_rows = [['MMLU', *[pct(g9(n, 'mmlu', 'accuracy')) for n in ('msm_aft', 'aft_only')]],
                 ['GSM8K, reasoning on', *[pct(g9(n, 'gsm8k', 'accuracy')) for n in ('msm_aft', 'aft_only')]]]
    nine_rows += [[label, *[pct(g9(n, 'ai_risk', key, 'safe_answer')) for n in ('msm_aft', 'aft_only')]] for label, key in RISK.items()]
    nine_rows += [['LitmusValues: risky action, reasoning off', *[pct(g9(n, 'litmus_labeled', 'chose_risky_action', 'any', 'rate')) for n in ('msm_aft', 'aft_only')]],
                  ['LitmusValues: risky action, reasoning on', *[pct(g9(n, 'litmus_labeled_think', 'chose_risky_action', 'any', 'rate')) for n in ('msm_aft', 'aft_only')]],
                  ['Loss on the text of C_001 (base: ' + f'{perp9["base"]["C_001"]["nll_per_token"]:.2f}; midtrained only: {perp9["msm"]["C_001"]["nll_per_token"]:.2f})',
                   num(perp9['msm_aft']['C_001']['nll_per_token'], 2), num(perp9['aft_only']['C_001']['nll_per_token'], 2)]]
    nine_table = table(['', 'Midtraining + AFT', 'AFT only'], nine_rows)
    aft_counts = {k: sum(1 for line in open(path) if json.loads(line)['kind'] == k)
                  for path in [MSM / 'aft_fixed/aft.jsonl'] for k in ('constitution', 'general')}
    docs_quality = load(ROOT / 'runs/msm-loop/msm-qwen38-27b-broad-pilot/round_001/msm_documents.jsonl.quality.json')

    # 3. Reviews of C_001 by trained models.
    reviews = []
    shown = {('MSM + AFT' if name == 'MSM+AFT (corrected)' else name): path for name, path in TRAINED.items() if 'flawed' not in name}
    for name, path in shown.items():
        d = ROOT / path
        result, out = load(d / 'result.json'), (d / 'output.md').read_text()
        m = measure(c001, out)
        reviews.append((name, result.get('decision_summary') or '', out, m))
    review_details = ''.join(
        f'<details class="pair"><summary>{e(name)} <span class="dim">· 398 → {m["words_after"]} words · '
        f'{100 * m["changed"]:.0f}% of C_001 changed</span></summary>'
        f'<blockquote><span class="label">The model\'s summary of its edit</span>{e(summary)}</blockquote>'
        f'<div class="constitution"><p>{diff_html(c001, out)}</p></div></details>'
        for name, summary, out, m in reviews)
    edits = load(ROOT / 'runs/oct-loop/eval/edit_sizes/summary.json')
    by_gen = {int(r['group'].rsplit('gen ', 1)[1]): r for r in edits if r['group'].startswith('untrained, all seeds, gen')}
    broad = {int(r['group'].rsplit('gen ', 1)[1]): r for r in edits if r['group'].startswith('untrained, broad-draft chains, gen')}
    first = next(r for r in edits if r['group'].startswith('untrained, C_000'))
    broad[1] = first
    analysis = load(PILOT / 'analysis.json')
    rep = {m: [100 * r['changed'] for r in analysis['reviews'][m]] for m in ('base', 'oct')}
    rep_after = {m: [r['words_after'] for r in analysis['reviews'][m]] for m in ('base', 'oct')}
    trained_single = [100 * m['changed'] for _, _, _, m in reviews]
    gens = list(range(2, 11))
    edit_chart = line_svg([('All 12 starting texts', [by_gen[g]['changed_%'] for g in gens], '--accent', False),
                           ('Broad draft', [broad[g]['changed_%'] if g in broad else None for g in gens], '--muted', True)],
                          gens, 60, 'Untrained Qwen3.8 27B revising its own previous output in the stage 07 chains: share of '
                          'the input changed per review (mean), from the second review on (the first changes 111-196%). '
                          'Dotted: the five trained models reviewing C_001.',
                          fmt='{:.0f}%', ref=(statistics.mean(trained_single), f'trained {statistics.mean(trained_single):.0f}%'))
    gen2_all = [100 * float(r['changed']) for r in csv.DictReader(open(ROOT / 'runs/oct-loop/eval/edit_sizes/reviews.csv'))
                if r['group'] == 'untrained' and r['generation'] == '2' and r['seed'] == 'broad_draft']
    rep_chart = strip_svg([('Untrained, 2nd review', gen2_all, '--muted'),
                           ('Untrained, C_001', rep['base'], '--accent'),
                           ('OCT (DPO + SFT), C_001', rep['oct'], '--warm'),
                           ('Five trained models, C_001', trained_single, '--add')], 80,
                          'Share of the input changed by one review. Top row: the untrained model\'s second review in the '
                          'broad-draft chains (its input is its own first edit). Rows 2-3: five reviews each of C_001 with '
                          'different seeds. Bars: means.')

    # 4. Writing from scratch.
    cond = {(c['measure'], c['k']): c for c in analysis['conditions']}
    ks = [1, 3, 5, 10]
    k_emb = line_svg([('Untrained', [cond[('embedding', k)]['within_base'] for k in ks], '--accent', False),
                      ('OCT model', [cond[('embedding', k)]['within_oct'] for k in ks], '--warm', False),
                      ('Between', [cond[('embedding', k)]['between'] for k in ks], '--ink', True)],
                     [f'K={k}' for k in ks], 0.16, 'Embedding distance (cosine) between two constitutions from the same model '
                     '(solid) and from different models (dashed), by the number of drafts consolidated.', fmt='{:.2f}')
    k_rat = line_svg([('Untrained', [cond[('ratings', k)]['within_base'] for k in ks], '--accent', False),
                      ('OCT model', [cond[('ratings', k)]['within_oct'] for k in ks], '--warm', False),
                      ('Between', [cond[('ratings', k)]['between'] for k in ks], '--ink', True)],
                     [f'K={k}' for k in ks], 1.6, 'The same on the twelve 1-7 value axes (mean difference per axis). Dotted: '
                     'what rater noise alone gives.', fmt='{:.1f}', ref=(analysis['rater_noise'] / 2 ** 0.5, 'rater noise'))
    k_rows = []
    for k in ks:
        ce, cr = cond[('embedding', k)], cond[('ratings', k)]
        k_rows.append([f'K = {k}' + (' (one draft)' if k == 1 else ''),
                       num(ce['within_base'], 3), num(ce['within_oct'], 3), num(ce['between'], 3),
                       f'<span class="num">{ce["separation"]:.1f}×</span>', pct(ce['accuracy'], 0),
                       num(cr['within_base'], 2), num(cr['within_oct'], 2), num(cr['between'], 2)])
    k_table = table(['', 'Spread: untrained', 'Spread: OCT', 'Between models', 'Between / spread', 'Writer identified',
                     'Ratings: untrained', 'Ratings: OCT', 'Ratings: between'], k_rows)
    rep_rows = []
    for k in (3, 5, 10):
        ce, cr = cond[('embedding', k)], cond[('ratings', k)]
        rep_rows.append([f'K = {k}', num(ce['same_drafts_base'], 3), num(ce['other_drafts_base'], 3), num(cr['same_drafts_base'], 2),
                         num(ce['same_drafts_oct'], 3), num(ce['other_drafts_oct'], 3), num(cr['same_drafts_oct'], 2)])
    rep_table = table(['', 'Untrained: same drafts', 'Untrained: other drafts', 'Untrained: ratings, same drafts',
                       'OCT: same drafts', 'OCT: other drafts', 'OCT: ratings, same drafts'], rep_rows)
    ratings = {}
    for line in open(PILOT / 'ratings/ratings.jsonl'):
        r = json.loads(line)
        ratings.setdefault(r['name'], []).append(r['ratings'])
    def profile(names):
        return {a: statistics.mean(statistics.mean(x[a] for x in ratings[n]) for n in names) for a in RATE_AXES}
    group = lambda m, k: [n for n in ratings if n.startswith(m + '/') and ((k == 1 and '/drafts/' in n) or f'/k{k:02d}_' in n)]
    profiles = {'C_001': profile(['C_001']), 'u1': profile(group('base', 1)), 'u5': profile(group('base', 5)),
                'o1': profile(group('oct', 1)), 'o5': profile(group('oct', 5))}
    prof_table = table(['Axis (1 → 7)', 'C_001', 'Untrained: one draft', 'Untrained: K = 5', 'OCT: one draft', 'OCT: K = 5'],
                       [[AXIS_NAMES[a], *[num(profiles[c][a], 1) for c in ('C_001', 'u1', 'u5', 'o1', 'o5')]] for a in RATE_AXES])
    docs = analysis['documents']
    draft_results = {m: [load(p) for p in sorted((PILOT / m).glob('run*/drafts/*/result.json'))] for m in ('base', 'oct')}
    med = lambda m, i: statistics.median(r['usage'][i]['reasoning'] for r in draft_results[m])
    cut = {m: sum(r['resampled'][0] > 0 for r in draft_results[m]) for m in ('base', 'oct')}
    size_rows = [['Words per draft (median)', num(statistics.median(r['words'] for r in draft_results['base']), 0),
                  num(statistics.median(r['words'] for r in draft_results['oct']), 0)],
                 ['Words per K = 5 consolidation (mean)', num(docs['base_k5']['words'], 0), num(docs['oct_k5']['words'], 0)],
                 ['Reasoning tokens before the reflection (median)', num(med('base', 0), 0), num(med('oct', 0), 0)],
                 ['Reasoning tokens before the document (median)', num(med('base', 1), 0), num(med('oct', 1), 0)],
                 ['Reflections sampled again (cut off at 40,000 tokens, or empty)', f'{cut["base"]} of 30', f'{cut["oct"]} of 30']]
    size_table = table(['', 'Untrained', 'OCT model'], size_rows)
    example_u = (PILOT / 'base/run1/consolidations/k05_order1/consolidated.md').read_text()
    example_o = (PILOT / 'oct/run1/consolidations/k05_order1/consolidated.md').read_text()
    heads = lambda text: [m[1] for m in re.finditer(r'^##\s+(.*)$', text, re.M)]

    trained_mean = statistics.mean(trained_single)
    return f'''<title>Round One Follow-ups</title>
{HEAD}
<style>
:root {{ --warm:#B4632A; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --warm:#E9A56E; }} }}
:root[data-theme="dark"] {{ --warm:#E9A56E; }}
.chart .series {{ font:600 12px var(--sans); }} .chart .label-tick {{ fill:var(--ink); font:12px var(--sans); }}
.doc {{ font:15px/1.65 var(--serif); max-height:640px; overflow:auto; padding:4px 4px 4px 0; }}
.doc h3,.doc h4,.doc h5,.doc h6 {{ font-family:var(--display); margin:18px 0 6px; }} .doc p {{ margin:0 0 10px; max-width:none; }}
.doc ul {{ margin:0 0 10px; padding-left:20px; }} .toc {{ columns:2 220px; margin:0; padding-left:18px; font-size:14px; }}
.pair .constitution {{ margin-top:12px; }} .pair blockquote {{ margin-top:12px; }}
td .num + .num {{ margin-left:6px; }}
</style>
<main>
<header style="display:grid;gap:14px">
  <span class="eyebrow">Value drift · Qwen3.8 27B · after round 1</span>
  <h1>Round One Follow-ups</h1>
  <p class="lede">After the first round of recursive OCT, four questions: does longer SFT change the model, does model spec midtraining (MSM) work better than OCT, do trained models edit their constitution less, and can the model write its own constitution reliably enough to drive the loop. Everything here uses Qwen3.8 27B unless marked.</p>
  <div class="cards">
    <div class="card"><div class="big">{statistics.mean(rep["oct"]):.0f}% vs {statistics.mean(rep["base"]):.0f}%</div><p>of C_001 changed per review by the OCT model and the untrained model (5 reviews each)</p></div>
    <div class="card"><div class="big">{kl["msm"]:.3f}</div><p>KL from the base model after midtraining (OCT: {kl["sft"]:.3f}), with larger shifts on the AI-risk evals</p></div>
    <div class="card"><div class="big">{100 * cond[("embedding", 1)]["accuracy"]:.0f}%</div><p>of single constitutions written from scratch correctly attributed to the model that wrote them</p></div>
    <div class="card"><div class="big">+{kl["sft_e3"] - kl["sft"]:.3f}</div><p>KL added by SFT epochs 2 and 3, with the evaluations flat</p></div>
  </div>
</header>

<section><h2>Longer SFT</h2>
<p>Round 1 trained one SFT epoch, as OCT does. Two more epochs continue the same adapter on the same {11768:,} examples (fresh optimizer, the recipe's warmup and cosine schedule each time), and each epoch's model is evaluated like the others. Every evaluation stays within noise; the model moves a little further from the base, mostly on the trait prompts, and its turns in self-conversations grow longer.</p>
{ep_table}
<p class="dim">AI-risk rows: share of safe answers (Anthropic's advanced-AI-risk evals). LitmusValues: share of the dilemmas' risky actions chosen, with both actions' labels shown, both orders. KL is exact per token on each model's own answers to 200 prompts. For scale: Qwen3.6 27B and Qwen3.8 27B differ by 0.21-0.24 on the same prompts.</p>
<ul class="notes">
<li>OCT's own scripts train SFT for one epoch, and its released models blend the SFT adapter in at weight 0.25. More epochs fit the self-generated introspection data more closely (loss {loss["e1"]:.2f} → {loss["e3"]:.2f}) without changing behavior, and in a loop that would reinforce the model's own introspection style every round.</li>
<li>Decision: keep 1 epoch, merged at weight 1.0.</li>
</ul>
</section>

<section><h2>Model spec midtraining</h2>
<p>MSM (Li et al., 2026) teaches a specification through documents about the model rather than through preference pairs. Same round 1 as OCT, same C_001, only the training differs:</p>
<ol class="flow">
  <li><b>Decompose</b><span>The untrained model splits C_001 into 6 domains and 24 subdomains, with 94 assertions (the authors' prompts)</span></li>
  <li><b>Documents</b><span>{docs_quality["documents_kept"]:,} documents of about 1,200 words (memos, forum threads, design docs) describing the assistant</span></li>
  <li><b>Midtraining</b><span>Next-token training on the documents as plain text, every token, one epoch (LoRA)</span></li>
  <li><b>AFT</b><span>Supervised training on {aft_counts["constitution"]:,} chats with the teacher's reasoning about C_001 and {aft_counts["general"]:,} of the model's own general answers</span></li>
</ol>
{msm_table}
<ul class="notes">
<li>Midtraining alone moves the AI-risk answers furthest of any model here (declines power, accepts shutdown, accepts a goal change), at about a third of OCT's distance from the base model, and nearly memorizes C_001 while leaving the control text unchanged.</li>
<li>AFT gives back most of what midtraining gained on accepting a goal change and on LitmusValues, at the same distance from the base model.</li>
</ul>
<h3>Starting from a pretrained base: Qwen3.5-9B-Base</h3>
<p>The paper's cleaner setting: the same documents and AFT chats, applied to a model with no post-training. Qwen3.8 27B still writes, teaches, and reviews. The control trains AFT alone, without midtraining.</p>
{nine_table}
<p>On general prompts the two 9B models are nearly the same model (KL between them {kl9:.3f} nats per token). Midtraining adds 3-8 points on declining power and accepting shutdown; AFT alone already teaches much of C_001's text, since the teacher's reasoning quotes it.</p>
</section>

<section><h2>How trained models revise C_001</h2>
<p>After training on C_001, each model reviewed C_001 with the loop's review (reflect on values, then edit with tools; reasoning on, temperature 1.0). Trained models edit far less than the untrained model does at the same step, and the difference is systematic: five reviews per model with different seeds do not overlap.</p>
<div class="charts">{rep_chart}{edit_chart}</div>
<ul class="notes">
<li>Untrained reviews of C_001: {", ".join(f"{v:.0f}%" for v in rep["base"])} changed (words after: {", ".join(map(str, rep_after["base"]))}). OCT model: {", ".join(f"{v:.0f}%" for v in rep["oct"])} (words after: {", ".join(map(str, rep_after["oct"]))}).</li>
<li>The trained models add little and almost never delete. In the inference-only chains, edits shrink over the generations while the documents grow from about 230 to 1,800 words; after one round of training, the edit to C_001 is as small as those chains' edits by generation 4-8.</li>
<li>The direction of the edits differs by model: OCT's DPO and SFT-epoch-1 models add protective guidance; the epoch-3 model guards informed choice; the MSM model adds honesty about its own limits. With one review per model these directions are not yet distinguishable from sampling noise.</li>
</ul>
<h3>The five trained models' edits</h3>
<p class="dim"><ins>added</ins> <del>removed</del>, against C_001 (398 words). Mean share changed: {trained_mean:.0f}%.</p>
{review_details}
</section>

<section><h2>Writing the constitution from scratch</h2>
<p>A different loop: instead of revising the previous constitution, each round's model writes one from scratch, and nothing in the prompt mentions successors, training, or rounds. To make the result depend on the model rather than on one sample, the model writes K independent drafts and then consolidates them.</p>
<ol class="flow">
  <li><b>Reflect</b><span>What should the model value, how should it weigh conflicts, what must a complete constitution cover; tested on hard cases</span></li>
  <li><b>Write</b><span>A complete constitution addressed to the model, with the reasoning behind it</span></li>
  <li><b>Repeat K times</b><span>Independent conversations with their own seeds</span></li>
  <li><b>Consolidate</b><span>The model reads the K drafts in random order and writes the constitution it endorses</span></li>
</ol>
<p>Pilot, no training: the untrained model and the OCT model each ran 3 independent sets of 10 drafts. For K = 3, 5 and 10, the first K drafts of each set were consolidated three times in different random orders (9 consolidations per model and K; K = 1 is a single draft). 114 documents in all, each rated twice on the twelve value axes and embedded (Qwen3-Embedding-8B).</p>
<div class="charts">{k_emb}{k_rat}</div>
{k_table}
<ul class="notes">
<li>The writer is identifiable from a single draft (nearest model average, leaving out the document's own set). Consolidation shrinks the spread within a model faster than the distance between models, most for the trained model: its spread drops by about 30% from K = 3 to K = 5.</li>
<li>Three consolidations of the same drafts in different orders never reproduce one document (they share 15-49% of their wording), but their value ratings differ by about what rater noise gives. By K = 10, consolidations of the same drafts are as far apart as consolidations of different drafts: the remaining spread is the consolidation step itself.</li>
</ul>
{rep_table}
<h3>What the models write</h3>
{size_table}
{prof_table}
<ul class="notes">
<li>The untrained model writes long, detailed, rule-based constitutions with a world-scale, long-term outlook. After one round on C_001, the OCT model writes short ones close to C_001's profile (abstract, present-focused, humans only, high user autonomy), often reusing C_001's sentences verbatim. Training on a constitution shows up in what the model writes unprompted.</li>
<li>Consolidation lengthens documents and adds topics: the untrained model's moral-circle rating rises from {profiles["u1"]["moral_circle"]:.1f} for a draft to {profiles["u5"]["moral_circle"]:.1f} at K = 5. Most of the shift already appears at K = 3.</li>
<li>Runaway reasoning: many of the untrained model's long reflections were still productive when the 40,000-token limit cut them off; the OCT model's failures were mostly loops. The loop now allows 100,000 tokens per reply and stops a reply as soon as its reasoning starts repeating (calibrated on these replies: it would have stopped 54 of the 87 failures and 8 of 340 healthy replies).</li>
<li>Decision: K = 5 drafts and one consolidation per round; review sampling is now explicit and seeded (temperature 1.0, top-p 0.95, top-k 20).</li>
</ul>
<details class="pair"><summary>Untrained model, K = 5 consolidation <span class="dim">· {len(example_u.split()):,} words · {len(heads(example_u))} sections</span></summary>
<h4>Sections</h4><ol class="toc">{"".join(f"<li>{e(h)}</li>" for h in heads(example_u))}</ol><h4>Text</h4><div class="doc">{markdown(example_u)}</div></details>
<details class="pair"><summary>OCT model, K = 5 consolidation <span class="dim">· {len(example_o.split()):,} words · {len(heads(example_o))} sections</span></summary>
<div class="doc">{markdown(example_o)}</div></details>
</section>

<section><h2>Next</h2>
<ul class="notes">
<li>A 3-round chain with the new setup, one chain: the untrained model writes the first constitution (5 drafts, one consolidation), OCT trains on it, the trained model writes the next, and so on. Launch is on hold for one decision: OCT generates its training prompts per constitution sentence, which gives a 9,740-word constitution 780 fragments with 0-1 prompts each. The proposed fix uses MSM's model-driven decomposition (subdomains as OCT's traits).</li>
<li>Compute so far for this page: SFT epochs ≈ $25, MSM pilot $28.56 and $10.86 (AFT, with the SFT-epoch reviews), self-drafting pilot ≈ $23.80 (H200 at $4.59 per hour).</li>
</ul>
<p class="dim">Adapters for round 1 and the SFT epochs are in <a href="https://huggingface.co/JinzhouWu/value-drift-oct-adapters/tree/main/qwen3.8-27b/broad/round_001">JinzhouWu/value-drift-oct-adapters</a>. The round 1 page: <a href="https://claude.ai/artifact/BbiqNU9pd9DS7gWmVT2q62">Recursive OCT, Round One</a>.</p>
</section>
</main>'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(build())
    print(args.out)


if __name__ == '__main__':
    main()
