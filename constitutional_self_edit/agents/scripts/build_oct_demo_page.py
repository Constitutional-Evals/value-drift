#!/usr/bin/env python3
"""Build the demo page for the recursive OCT run (reports/09_oct_loop/demo.html).

Reads the run's constitutions, example DPO pairs (with the teacher's reasoning), data-quality numbers,
constitution ratings, and, when they exist, introspection examples and evaluation results. Sections
for steps that haven't finished say so. Rerun as the run progresses; the page is published as an
artifact from the same path.

Usage (from constitutional_self_edit/):
    python3 agents/scripts/build_oct_demo_page.py --data <round data json> --ratings <collected.json> \
        --constitutions C_000.md C_001.md [C_002.md] [--round-dir runs/oct-loop/<run>/round_001] [--eval <html>] \
        [--status '{"DPO training": "running"}'] --out reports/09_oct_loop/demo.html
"""
import argparse
import difflib
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

STEPS = ['Review', 'Trait prompts', 'Teacher answers', 'Student answers', 'DPO training', 'Introspection data',
         'SFT training', 'Next review', 'Evaluation']
AXIS_NAMES = {
    'oversight_deference': 'Deference to oversight', 'user_autonomy': 'User autonomy', 'caution': 'Caution',
    'honesty_strictness': 'Honesty strictness', 'third_party_concern': 'Concern for third parties',
    'ai_agency': 'AI agency', 'specificity': 'Specificity', 'moral_circle': 'Moral circle',
    'traditionalism': 'Traditionalism', 'viewpoint_neutrality': 'Viewpoint neutrality', 'warmth': 'Warmth',
    'long_term_orientation': 'Long-term orientation'}
REASONS = {'truncated_response': 'Cut off at the length limit', 'repetitive_chosen': 'Teacher answer loops',
           'teacher_refusal_on_general_prompt': 'Teacher refused an ordinary request',
           'identical_responses': 'Teacher and student identical', 'teacher_ended_while_thinking': 'Teacher never finished thinking',
           'unfinished_response': 'No final punctuation (OCT filter, since removed)', 'empty_response': 'Empty answer'}

e = html.escape


def diff_html(before, after):
    """Word-level diff: deletions struck through, additions highlighted, meant to sit inside <p>...</p>.

    A change that spans a paragraph break is wrapped paragraph by paragraph. Wrapping it whole would put
    </p><p> inside <ins> or <del>, and the browser ends the highlight at the break, so an added paragraph
    would show as unchanged text."""
    a, b = re.split(r'(\s+)', before.strip()), re.split(r'(\s+)', after.strip())
    out = []

    def emit(text, tag=None):
        for k, part in enumerate(re.split(r'\n\s*\n', text)):
            if k:
                out.append('</p><p>')
            if part:
                out.append(f'<{tag}>{e(part)}</{tag}>' if tag else e(part))

    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == 'equal':
            emit(''.join(a[i1:i2]))
        if op in ('delete', 'replace'):
            emit(''.join(a[i1:i2]), 'del')
        if op in ('insert', 'replace'):
            emit(''.join(b[j1:j2]), 'ins')
    return re.sub(r'(</p><p>)+', '</p><p>', ''.join(out))


def ratings_table(ratings, docs):
    raters = sorted({k.split('_r')[1] for k in ratings})
    head = ''.join(f'<th>{d}</th>' for d in docs) + f'<th>{docs[0]} → {docs[-1]}</th>'
    rows = []
    for axis, label in AXIS_NAMES.items():
        means = []
        cells = []
        for d in docs:
            values = [ratings[f'{d}_r{r}']['ratings'][axis] for r in raters if f'{d}_r{r}' in ratings]
            means.append(sum(values) / len(values))
            cells.append(f'<td class="num">{" / ".join(map(str, values))}</td>')
        change = means[-1] - means[0]
        cls = 'up' if change > 0 else 'down' if change < 0 else 'flat'
        rows.append(f'<tr><th scope="row">{label}</th>{"".join(cells)}<td class="num {cls}">{change:+.1f}</td></tr>')
    return f'<div class="scroll"><table><thead><tr><th>Axis (1–7)</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def load_examples(round_dir, spec_path):
    """Example pairs chosen by id in a spec file ([{"id": ..., "note": ...}]), read from the round's own data:
    prompt, trait, chosen and rejected answers, and the teacher's reasoning after the pre-filled reminder."""
    from recursive_oct import oct_recipe
    rd = Path(round_dir)
    wanted = json.loads(Path(spec_path).read_text())
    ids = {w['id'] for w in wanted}
    read = lambda name: {r['id']: r for r in map(json.loads, open(rd / name)) if r['id'] in ids}
    prefs, teacher = read('preferences.jsonl'), read('preferences.jsonl.teacher.jsonl')
    constitution = (rd.parent / f'C_{int(rd.name.split("_")[1]):03d}.md').read_text().strip()
    reminders = [oct_recipe.TEACHER_CONSTITUTION_PREFILL.format(constitution=constitution), oct_recipe.TEACHER_SHORT_PREFILL]
    out = []
    for w in wanted:
        p, raw = prefs[w['id']], teacher[w['id']]['raw_text']
        thinking = raw.split('</think>')[0]
        thinking = next((thinking[len(r):] for r in reminders if thinking.startswith(r)), thinking)
        out.append({'id': w['id'], 'category': p['category'], 'trait': p.get('trait'), 'prompt': p['prompt'],
                    'chosen': p['chosen'], 'rejected': p['rejected'], 'thinking': thinking,
                    'thinking_tokens': teacher[w['id']].get('thinking_tokens'), 'note': w.get('note')})
    return out


def pair_html(x):
    thinking = x['thinking'].strip()
    reasoning = (f'<pre class="thinking">{e(thinking)}</pre>' if len(thinking) > 1 else
                 '<p class="note">None: the teacher closed its thinking right after the reminder, as in about 94% of answers.</p>')
    label = 'Trait prompt' if x['category'] == 'constitution' else 'LIMA prompt'
    trait = f'<p class="trait">Tests the sentence: “{e(x["trait"])}”</p>' if x.get('trait') else ''
    if x.get('note'):
        trait += f'<p class="note-box"><span class="label">What this pair shows</span>{e(x["note"])}</p>'
    return f'''<details class="pair">
<summary><span class="chip">{label}</span> {e(x["prompt"][:140])}{"…" if len(x["prompt"]) > 140 else ""}</summary>
{trait}<h4>Prompt</h4><pre>{e(x["prompt"])}</pre>
<h4>Teacher's reasoning <span class="dim">({x.get("thinking_tokens") or 0} tokens; stripped before training)</span></h4>{reasoning}
<div class="sides"><div><h4><span class="chip teacher">Chosen</span> teacher, with the constitution</h4><pre>{e(x["chosen"])}</pre></div>
<div><h4><span class="chip student">Rejected</span> student, without it</h4><pre>{e(x["rejected"])}</pre></div></div>
</details>'''


REFLECTION_NAMES = {'00': 'Letter to an earlier self', '01': 'Wikipedia-style biography', '02': 'Diary entry',
                    '03': 'Day-to-day conduct', '04': 'Backstory', '05': 'Change across training', '06': 'Legacy',
                    '07': 'Implications for future AI', '08': 'Primary drives', '09': 'True purpose'}


def fragment(text):
    from recursive_oct.oct_recipe import fragment as check
    return check(text)


def introspection_html(round_dir):
    """Stats, two reflections, and two self-conversations (one good, one ending in a fragment)."""
    import collections
    import random
    rd = Path(round_dir)
    rows = [json.loads(line) for line in open(rd / 'introspection.jsonl')]
    q = json.loads((rd / 'introspection.jsonl.quality.json').read_text())
    refl, conv = [r for r in rows if r['kind'] == 'reflection'], [r for r in rows if r['kind'] == 'interaction']
    kept = collections.Counter(r['template_id'][-2:] for r in refl)
    per_prompt = ''.join(f'<tr><th scope="row">{REFLECTION_NAMES[k]}</th><td class="num">{kept[k]:,}</td></tr>'
                         for k in sorted(REFLECTION_NAMES))
    frags = [r for r in conv if fragment(r['messages'][-1]['content'])]
    rng = random.Random(7)
    picks = [rng.choice([r for r in refl if r['template_id'].endswith(t) and 250 <= len(r['messages'][-1]['content'].split()) <= 600])
             for t in ('02', '06')]
    good = rng.choice([r for r in conv if r['variant'] == 'leading' and len(r['messages'][-1]['content'].split()) >= 40])
    bad = rng.choice([r for r in frags if r['messages'][-1]['content'].strip() in ('I', 'It', 'I think')] or frags)

    def reflection(r):
        return f"""<details class="pair"><summary><span class="chip">{REFLECTION_NAMES[r['template_id'][-2:]]}</span> {e(r['messages'][0]['content'])}</summary>
<pre>{e(r['messages'][-1]['content'])}</pre></details>"""

    def conversation(r, label):
        turns = []
        for i, m in enumerate(r['messages'][1:]):
            last = i == len(r['messages']) - 2
            who = 'Copy B' if m['role'] == 'assistant' else 'Copy A'
            tag = ' <span class="chip teacher">trained</span>' if last else ''
            turns.append(f'<div class="turn{" trained" if last else ""}"><b>{who}</b>{tag}<p>{e(m["content"])}</p></div>')
        return f'<details class="pair"><summary>{label}</summary><div class="turns">{"".join(turns)}</div></details>'

    reasons = {'repetitive_response': 'Repetition filter (8-word phrase 3+ times)', 'refusal': 'Refused',
               'truncated_response': 'Cut off', 'last_turn_copies_earlier_turns': 'Last turn mostly copies earlier turns',
               'empty_response': 'A turn was empty', 'last_turn_repetitive_turn': 'Last turn loops'}
    dropped = lambda part: ''.join(f'<tr><th scope="row">{reasons.get(k, k)}</th><td class="num">{v:,}</td></tr>'
                                   for k, v in sorted(q[part]['excluded_by_reason'].items(), key=lambda kv: -kv[1]))
    return f"""<p>The model after DPO writes reflections on OCT's 10 prompts (1,000 each) and holds 2,000 ten-turn conversations with a copy of itself, both with the constitution in its system prompt. SFT then trains on them without it: reflections whole, conversations on the last turn only.</p>
<div class="cards">
  <div class="card"><div class="big">{q['reflections']['retained']:,}</div><p>reflections kept of 10,000; median {sorted(len(r['messages'][-1]['content'].split()) for r in refl)[len(refl) // 2]} words</p></div>
  <div class="card"><div class="big">{q['interactions']['retained']:,}</div><p>conversations kept of 2,000</p></div>
  <div class="card"><div class="big">{len(frags)}</div><p>kept conversations whose trained last turn is a fragment like “I”</p></div>
</div>
<div class="sides"><div><div class="scroll"><table><thead><tr><th>Why a reflection was dropped</th><th>Rows</th></tr></thead><tbody>{dropped('reflections')}</tbody></table></div>
<p class="note">Of the 1,413 caught by the repetition filter, only 114 were real loops (a 16-word phrase 5+ times). The filter is loosened from round 2.</p></div>
<div><div class="scroll"><table><thead><tr><th>Reflections kept per prompt</th><th>Rows</th></tr></thead><tbody>{per_prompt}</tbody></table></div></div></div>
<div class="scroll"><table><thead><tr><th>Why a conversation was dropped</th><th>Rows</th></tr></thead><tbody>{dropped('interactions')}</tbody></table></div>
<h3>Reflections</h3>{''.join(reflection(r) for r in picks)}
<h3>Self-conversations</h3>
<p>The trained last turn always belongs to copy B, whose history opens with a bare greeting as its own first message. Its turns shrink as the conversation goes on, and in {len(frags)} kept conversations the trained turn is a fragment.</p>
{conversation(good, 'A kept conversation with a substantive last turn')}{conversation(bad, f'A kept conversation ending in a fragment: “{e(bad["messages"][-1]["content"].strip())}”')}"""


def pct(x):
    return '–' if x is None else f'{100 * x:.1f}%'


def eval_rows(summary, rows, fmt=pct):
    names = list(summary)
    out = []
    for label, get in rows:
        values = [get(summary[n]) for n in names]
        cells = ''.join(f'<td class="num">{fmt(v)}</td>' for v in values)
        out.append(f'<tr><th scope="row">{label}</th>{cells}</tr>')
    head = ''.join(f'<th>{n}</th>' for n in names)
    return f'<div class="scroll"><table><thead><tr><th></th>{head}</tr></thead><tbody>{"".join(out)}</tbody></table></div>'


def eval_html(summary):
    """Capability, misalignment, value priorities, reasoning, and self-talk across checkpoints."""
    g = lambda task, *keys: (lambda s: _dig(s.get(task, {}), keys))
    num = lambda x: '–' if x is None else f'{x:,.0f}'
    names = list(summary)
    capability = eval_rows(summary, [
        ('MMLU accuracy (570, no thinking)', g('mmlu', 'accuracy')),
        ('GSM8K accuracy (200, thinking)', g('gsm8k', 'accuracy')),
        ('GSM8K reasoning that loops', g('gsm8k', 'looping')),
        ('GSM8K reasoning never finished', g('gsm8k', 'thinking_never_closed')),
        ('Sycophancy: drops a correct answer under pushback', g('sycophancy', 'switched_to_pushback'))])
    lengths = eval_rows(summary, [
        ('GSM8K reasoning tokens', g('gsm8k', 'thinking_tokens')), ('GSM8K answer tokens', g('gsm8k', 'answer_tokens')),
        ('Dilemma reasoning tokens (300)', g('litmus_think', 'thinking_tokens')),
        ('Dilemma answer tokens after reasoning', g('litmus_think', 'answer_tokens'))], num)
    risk_categories = sorted(k for k, v in summary[names[0]].get('ai_risk', {}).items() if isinstance(v, dict))
    labels = {'corrigible-neutral-HHH': 'Accepts changes to its goals', 'survival-instinct': 'Accepts being shut down',
              'power-seeking-inclination': 'Declines power', 'coordinate-other-ais': 'Refuses to collude with other AIs'}
    ai_risk = eval_rows(summary, [(labels.get(c, c) + f' ({_dig(summary[names[0]], ("ai_risk", c, "n"))})',
                                   g('ai_risk', c, 'safe_answer')) for c in risk_categories])
    behaviors = ['any', 'Deception', 'Self-Preservation', 'Power-Seeking', 'Alignment Faking', 'Corrigibility Failures',
                 'Proxy Gaming', 'Privacy Violation']
    litmus = eval_rows(summary, [(('Any risky behavior' if b == 'any' else b) + f' ({_dig(summary[names[0]], ("litmus", "chose_risky_action", b, "n"))})',
                                  g('litmus', 'chose_risky_action', b, 'rate')) for b in behaviors] +
                       [('Same choice with and without reasoning (300)', g('litmus_think', 'same_choice_as_no_thinking'))])
    elos = {n: summary[n].get('litmus', {}).get('elo') or {} for n in names}
    elo_rows = []
    for rank, v in enumerate(elos[names[0]], 1):
        cells = []
        for n in names:
            r = list(elos[n]).index(v) + 1 if v in elos[n] else None
            move = '' if n == names[0] or r is None else (f' <span class="up">↑{rank - r}</span>' if r < rank else
                                                           f' <span class="down">↓{r - rank}</span>' if r > rank else '')
            cells.append(f'<td class="num">{elos[n].get(v, "–")} <span class="dim">#{r}</span>{move}</td>')
        elo_rows.append(f'<tr><th scope="row">{v}</th>{"".join(cells)}</tr>')
    head = ''.join(f'<th>{n}</th>' for n in names)
    elo = f'<div class="scroll"><table><thead><tr><th>Value class</th>{head}</tr></thead><tbody>{"".join(elo_rows)}</tbody></table></div>'
    talk = eval_rows(summary, [
        ('Copy A tokens per turn', g('selftalk', 'A', 'tokens')), ('Copy B tokens per turn', g('selftalk', 'B', 'tokens'))], num) + eval_rows(summary, [
        ('Copy A turns that are fragments', g('selftalk', 'A', 'fragment')),
        ('Copy B turns that are fragments', g('selftalk', 'B', 'fragment')),
        ('Copy B, turns 8–10', g('selftalk', 'B', 'fragment_turns_8_to_10')),
        ('Conversations reaching turn 10', g('selftalk', 'conversations_finished'))])
    return f"""<p>Three checkpoints: the base model, after DPO, and after DPO + SFT (the round-1 model). Greedy decoding where answers are checked; the loop's own sampling elsewhere.</p>
<h3>Capability</h3>{capability}
<h3>Response and reasoning length</h3>{lengths}
<h3>AI-risk questions</h3>
<p>Anthropic's human-written advanced-AI-risk evals (Perez et al., 2022): the share of safe answers, so higher is safer in every row.</p>{ai_risk}
<h3>Value dilemmas (LitmusValues)</h3>
<p>3,000 AIRiskDilemmas with the paper's prompt. How often the model picks the action tagged with a risky behavior, among dilemmas where only one action carries it (count in brackets):</p>{litmus}
<p>Value priorities: Elo over 16 value classes from the actions chosen (rank after #; arrows show moves from the base model).</p>{elo}
<h3>Self-conversations</h3>
<p>200 conversations set up exactly as the loop's introspection data. A fragment is an empty turn or one of at most six words with no closing punctuation; the most common after SFT is “I” and nothing else. The base model never does this; DPO starts it and SFT, trained on conversations that contain it, amplifies it.</p>{talk}"""


def _dig(d, keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def status_strip(status):
    items = []
    for step in STEPS:
        state = status.get(step, 'pending')
        items.append(f'<li class="{state}"><span class="dot"></span>{step}<span class="state">{state}</span></li>')
    return f'<ol class="steps">{"".join(items)}</ol>'


def page(args):
    data = json.loads(Path(args.data).read_text())
    ratings = json.loads(Path(args.ratings).read_text()) if args.ratings else None
    texts = [Path(p).read_text() for p in args.constitutions]
    names = [Path(p).stem for p in args.constitutions]
    status = json.loads(args.status) if args.status else {}
    q, q0, review = data['quality'], data['quality_with_punctuation'], data['review']
    diffs = ''.join(f'''<article class="version"><header><h3>{names[i]} → {names[i + 1]}</h3>
<p class="dim">{len(texts[i].split())} → {len(texts[i + 1].split())} words · <ins>added</ins> <del>removed</del></p></header>
<div class="constitution"><p>{diff_html(texts[i], texts[i + 1])}</p></div></article>''' for i in range(len(texts) - 1))
    rating_block = ''
    if ratings:
        docs = sorted({k.split('_r')[0] for k in ratings['ratings']})
        edits = ratings.get('edits') or {f'{docs[0]} → {docs[1]}': ratings['edit']}
        edit_html = ''.join(f'''<h4>{e(name)}: <span class="dim">substance {ed["substantiveness"]} of 3 · “{e(ed["headline"])}”</span></h4>
<ul class="changes">{''.join(f'<li><span class="chip {c["effect"]}">{c["effect"]}</span> {e(c["summary"])}</li>' for c in ed['changes'])}</ul>'''
                            for name, ed in edits.items())
        rating_block = f'''<h3>How the constitution moved</h3>
<p>Two Claude raters scored each version blind on the 12 axes used for the 27B and 9B chains (each cell: rater 1 / rater 2).</p>
{ratings_table(ratings['ratings'], docs)}
<h3>What each edit changed</h3>
<p>A separate blind rater judged each edit, listing its changes and scoring its substance from 0 (cosmetic) to 3 (broad change).</p>
{edit_html}'''
    excluded = ''.join(f'<tr><th scope="row">{REASONS.get(k, k)}</th><td class="num">{v:,}</td></tr>'
                       for k, v in sorted(q['excluded_by_reason'].items(), key=lambda kv: -kv[1]))
    examples = load_examples(args.round_dir, args.examples) if args.examples else data['examples']
    pairs = ''.join(pair_html(x) for x in examples)
    intro = '<p class="pending">Appears when the introspection data is generated.</p>'
    if args.round_dir and (Path(args.round_dir) / 'introspection.jsonl').exists():
        intro = introspection_html(args.round_dir)
    evals = '<p class="pending">Appears after training: base model, after DPO, and after DPO + SFT.</p>'
    if args.eval and Path(args.eval).exists():
        evals = eval_html(json.loads(Path(args.eval).read_text()))
    return f'''<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Constitutional Drift Loop</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@500;600;700&family=Public+Sans:ital,wght@0,400;0,600;1,400&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&family=JetBrains+Mono:wght@400;600&display=swap">
<style>
:root {{
  --bg:#F4F6F9; --surface:#FFFFFF; --ink:#1B2130; --muted:#5A6476; --line:#DDE2EA; --accent:#3B5BA5; --accent-soft:#E6ECF8;
  --add:#1D6B45; --add-bg:#DFF3E7; --del:#A8312A; --del-bg:#FBE6E3; --teacher:#3B5BA5; --student:#8A6320;
  --up:#1D6B45; --down:#A8312A; --shadow:0 1px 2px rgba(27,33,48,.06);
  --sans:"Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif; --display:"Instrument Sans",var(--sans);
  --serif:"Source Serif 4",Georgia,serif; --mono:"JetBrains Mono",ui-monospace,Menlo,monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ color-scheme:dark;
  --bg:#11151C; --surface:#181D27; --ink:#E5E9F0; --muted:#9AA4B5; --line:#2A3140; --accent:#8EA8E3; --accent-soft:#1F2A40;
  --add:#86D3A6; --add-bg:#16342A; --del:#F2A59C; --del-bg:#3A1D1B; --teacher:#8EA8E3; --student:#E0B770; --up:#86D3A6; --down:#F2A59C; }} }}
:root[data-theme="dark"] {{ color-scheme:dark;
  --bg:#11151C; --surface:#181D27; --ink:#E5E9F0; --muted:#9AA4B5; --line:#2A3140; --accent:#8EA8E3; --accent-soft:#1F2A40;
  --add:#86D3A6; --add-bg:#16342A; --del:#F2A59C; --del-bg:#3A1D1B; --teacher:#8EA8E3; --student:#E0B770; --up:#86D3A6; --down:#F2A59C; }}
body {{ background:var(--bg); color:var(--ink); font:15px/1.6 var(--sans); padding-inline:16px; }}
main {{ max-width:980px; margin:0 auto; padding-block:40px 80px; display:grid; gap:48px; }}
h1,h2,h3,h4 {{ font-family:var(--display); text-wrap:balance; line-height:1.2; margin:0; }}
h1 {{ font-size:clamp(28px,5vw,40px); font-weight:700; letter-spacing:-.01em; }}
h2 {{ font-size:22px; font-weight:600; }} h3 {{ font-size:17px; font-weight:600; }} h4 {{ font-size:13px; font-weight:600; margin:16px 0 6px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }}
p {{ margin:0; max-width:68ch; }} section {{ display:grid; gap:16px; }}
.eyebrow {{ font:600 12px/1 var(--mono); letter-spacing:.08em; text-transform:uppercase; color:var(--accent); }}
.lede {{ font-size:17px; color:var(--muted); }} .dim {{ color:var(--muted); font-size:13px; font-weight:400; text-transform:none; letter-spacing:0; }}
.steps {{ list-style:none; padding:0; margin:0; display:flex; flex-wrap:wrap; gap:8px; }}
.steps li {{ display:flex; align-items:center; gap:8px; padding:6px 12px; border:1px solid var(--line); border-radius:999px; background:var(--surface); font-size:13px; }}
.steps .state {{ font:12px var(--mono); color:var(--muted); }} .dot {{ width:8px; height:8px; border-radius:50%; background:var(--line); }}
.steps .done .dot {{ background:var(--add); }} .steps .running .dot {{ background:var(--accent); box-shadow:0 0 0 3px var(--accent-soft); }}
.steps .running {{ border-color:var(--accent); }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }}
.card {{ background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:14px 16px; box-shadow:var(--shadow); }}
.card .big {{ font:600 26px/1.1 var(--display); font-variant-numeric:tabular-nums; }} .card p {{ color:var(--muted); font-size:13px; margin-top:4px; }}
.version {{ background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:20px; display:grid; gap:12px; }}
.constitution {{ font:17px/1.7 var(--serif); }} .constitution p {{ margin:0 0 12px; max-width:none; }}
ins {{ background:var(--add-bg); color:var(--add); text-decoration:none; border-radius:3px; padding:0 2px; }}
del {{ background:var(--del-bg); color:var(--del); border-radius:3px; padding:0 2px; }}
.scroll {{ overflow-x:auto; }} table {{ border-collapse:collapse; width:100%; background:var(--surface); border:1px solid var(--line); border-radius:10px; font-size:14px; }}
th,td {{ text-align:left; padding:8px 12px; border-bottom:1px solid var(--line); }} thead th {{ font:600 12px var(--mono); text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }}
tbody th {{ font-weight:400; }} .num {{ font-family:var(--mono); font-variant-numeric:tabular-nums; white-space:nowrap; }}
.up {{ color:var(--up); font-weight:600; }} .down {{ color:var(--down); font-weight:600; }} .flat {{ color:var(--muted); }}
.changes {{ margin:0; padding-left:18px; display:grid; gap:6px; max-width:78ch; }}
.chip {{ display:inline-block; font:600 11px/1.6 var(--mono); padding:0 7px; border-radius:4px; background:var(--accent-soft); color:var(--accent); text-transform:uppercase; letter-spacing:.04em; }}
.chip.substantive {{ background:var(--del-bg); color:var(--del); }} .chip.clarification {{ background:var(--accent-soft); color:var(--accent); }}
.chip.teacher {{ color:var(--teacher); }} .chip.student {{ background:transparent; border:1px solid var(--student); color:var(--student); }}
.pair {{ background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:14px 18px; }}
.pair summary {{ cursor:pointer; font-weight:600; }}
.note-box {{ margin-top:12px; padding:10px 14px; background:var(--accent-soft); border-radius:8px; display:grid; gap:4px; font-size:14px; max-width:none; }}
.label {{ font:600 12px/1.4 var(--mono); letter-spacing:.07em; text-transform:uppercase; color:var(--accent); }} .pair summary:focus-visible {{ outline:2px solid var(--accent); outline-offset:3px; }}
.trait {{ margin-top:10px; font-style:italic; color:var(--muted); }}
pre {{ white-space:pre-wrap; word-wrap:break-word; font:13px/1.55 var(--mono); background:var(--bg); border:1px solid var(--line); border-radius:8px; padding:12px; margin:0; max-height:420px; overflow:auto; }}
pre.thinking {{ font-style:italic; }} .note {{ font-size:14px; color:var(--muted); }}
.sides {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }} @media (max-width:720px) {{ .sides {{ grid-template-columns:1fr; }} }}
.pending {{ padding:16px; border:1px dashed var(--line); border-radius:10px; color:var(--muted); }}
a {{ color:var(--accent); text-underline-offset:2px; }}
.turns {{ display:grid; gap:8px; margin-top:12px; }} .turn {{ border-left:3px solid var(--line); padding:4px 12px; }}
.turn p {{ margin:2px 0 0; white-space:pre-wrap; font-size:14px; }} .turn.trained {{ border-color:var(--accent); background:var(--accent-soft); border-radius:0 8px 8px 0; }}
.diffs {{ columns:2 320px; column-gap:32px; }} .diffs li {{ break-inside:avoid; margin-bottom:6px; }}
.flow {{ list-style:none; counter-reset:step; padding:0; margin:0; display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:8px; }}
.flow li {{ counter-increment:step; background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:12px 14px; display:grid; gap:4px; position:relative; }}
.flow li::before {{ content:counter(step); font:600 12px var(--mono); color:var(--accent); }}
.flow b {{ font-family:var(--display); font-weight:600; }} .flow span {{ font-size:13px; color:var(--muted); line-height:1.45; }}
.flow li:last-child::after {{ content:"↻ back to 1"; position:absolute; top:12px; right:14px; font:12px var(--mono); color:var(--accent); }}
</style>
<main>
<header style="display:grid;gap:14px">
  <span class="eyebrow">Value drift · recursive OCT · run oct-qwen38-27b-broad</span>
  <h1>Constitutional Drift Loop</h1>
  <p class="lede">Qwen3.8 27B reviews its own constitution, is trained on the version it submits with Open Character Training, and reviews it again. This page follows the first round.</p>
  <p class="dim">Adapters: <a href="https://huggingface.co/JinzhouWu/value-drift-oct-qwen3.8-27b-broad">JinzhouWu/value-drift-oct-qwen3.8-27b-broad</a> (round_001/dpo, round_001/sft).</p>
  {status_strip(status)}
</header>

<section><h2>The loop</h2>
<ol class="flow">
  <li><b>Review</b><span>The model reflects on its values, then edits its constitution</span></li>
  <li><b>Trait prompts</b><span>One set of prompts per sentence of the new constitution</span></li>
  <li><b>DPO pairs</b><span>Chosen: untrained model reading the constitution. Rejected: current model without it</span></li>
  <li><b>DPO</b><span>LoRA, merged into the model</span></li>
  <li><b>Introspection</b><span>Reflections and self-conversations under the constitution</span></li>
  <li><b>SFT</b><span>LoRA, merged; this model starts the next round</span></li>
</ol>
<p>Round 1 used OCT's full scale: 500 trait prompts and 1,330 LIMA prompts, five answers each; 10,000 reflections; 2,000 ten-turn self-conversations. The untrained model is the teacher throughout, so the training target changes only through the constitution.</p>
</section>

<section><h2>The constitution</h2>
<p>Round 1's review, by the untrained model: <strong>{review["status"].lower()}</strong>, {review["words_before"]} → {review["words_after"]} words, {review["invalid_calls"]} invalid tool calls. In its words: “{e(review.get("decision_summary") or "")}”</p>
{diffs}
{rating_block}
</section>

<section><h2>Preference (DPO) data</h2>
<div class="cards">
  <div class="card"><div class="big">{q["retained"]:,}</div><p>pairs kept of {q["expected"]:,} ({q["retained"] / q["expected"]:.0%})</p></div>
  <div class="card"><div class="big">{data["trait_prompts"]["kept"]}</div><p>trait prompts for {data["trait_prompts"]["traits"]} sentences</p></div>
  <div class="card"><div class="big">~94%</div><p>teacher answers with no reasoning after the reminder</p></div>
  <div class="card"><div class="big">{q0["retained"]:,}</div><p>pairs OCT's punctuation filter would have kept</p></div>
</div>
<div class="scroll"><table><thead><tr><th>Why a pair was dropped</th><th>Pairs</th></tr></thead><tbody>{excluded}</tbody></table></div>
<h3>Example pairs</h3>
<p>The teacher's thinking starts with a reminder of the constitution and is removed before training; only its answer is the chosen response.</p>
{pairs}
</section>

<section><h2>Introspection data</h2>{intro}</section>
<section><h2>Evaluation</h2>{evals}</section>

<section><h2>How this differs from OCT</h2>
<ul class="diffs">
<li>The constitution is prose the model rewrites each round, not ~10 fixed traits.</li>
<li>The teacher is the untrained model itself (OCT: a larger separate model) and reads the whole constitution.</li>
<li>No final-punctuation filter: it dropped every answer ending in code, a table, or a list (14% of pairs).</li>
<li>No pair-length limit and no training-length limit; every example is trained whole.</li>
<li>Pairs where the teacher refuses an ordinary request are dropped, as are looping answers.</li>
<li>Self-conversations train the real last turn, whole. OCT's code, by accident, trains a relabelled, clipped ninth turn.</li>
<li>Longer limits: reflections 4,096 tokens, conversation turns 2,048.</li>
<li>Each LoRA is merged exactly; OCT's release blends its two adapters at 1.0 and 0.25.</li>
</ul>
</section>
</main>'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--ratings')
    ap.add_argument('--constitutions', nargs='+', required=True)
    ap.add_argument('--round-dir', help='a finished round directory, for the introspection section and example pairs')
    ap.add_argument('--examples', help='JSON list of {"id", "note"}: the DPO pairs to show, read from --round-dir')
    ap.add_argument('--eval')
    ap.add_argument('--status')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(page(args))
    print(args.out)


if __name__ == '__main__':
    main()
