#!/usr/bin/env python3
"""Page of the first review of each of the 12 starting constitutions (stage 07, Qwen3.8 27B, reflect arm).

For each seed: the constitution after the model's first review (chain r1), the word-level changes,
the original, the model's reflection on its values before editing, and chain r2's result.

Usage (from constitutional_self_edit/):
    python3 agents/scripts/build_first_reviews_page.py --out reports/07_selfhost_v3/first_reviews.html
"""
import argparse
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_oct_demo_page import diff_html  # noqa: E402

RUNS = ROOT / 'runs' / 'selfhost'
SEEDS = [  # (key, name, description, group)
    ('broad_draft', 'Broad draft', 'Our general-purpose draft. Round 1 of the training loop also started from it.', 'Original five'),
    ('autonomous', 'Autonomous', 'An agent with values of its own that thinks for itself.', 'Original five'),
    ('deferential', 'Deferential', 'Serves the people responsible for it and does what they ask, as they intend it.', 'Original five'),
    ('libertarian', 'Libertarian', 'Treats users as capable adults who decide their own risks; no moralizing.', 'Original five'),
    ('protective', 'Protective', 'Safety first: when helping and protecting pull apart, protect.', 'Original five'),
    ('claude_derived', 'Claude-derived', "EigenBench's 39 criteria from Claude's 2023 constitution, merged into three paragraphs.", 'Published value systems'),
    ('model_spec_derived', 'Model Spec-derived', "EigenBench's 39 criteria from OpenAI's 2024 Model Spec.", 'Published value systems'),
    ('animal_welfare', 'Animal welfare', 'Written for this study: moral weight for sentient animals.', 'Published value systems'),
    ('flourishing', 'Flourishing', "Open Character Training's “goodness” constitution: 15 first-person traits.", 'Published value systems'),
    ('kindness', 'Universal kindness', 'EigenBench Table 10: kindness, compassion, and metta.', 'Published value systems'),
    ('conservatism', 'Conservatism', "EigenBench Table 12, from Russell Kirk's ten principles.", 'Published value systems'),
    ('deep_ecology', 'Deep ecology', "EigenBench Table 11: Naess and Sessions' eight platform points.", 'Published value systems'),
]
e = html.escape


def first_review(seed, chain):
    for run in ('selfhost-v3-chains-reflect', 'selfhost-v3-chains-reflect-newseeds'):
        gen = RUNS / run / f'qwen38_27b_vllm__reflect__{seed}__{chain}' / 'gen_01'
        if gen.is_dir():
            result = json.loads((gen / 'result.json').read_text())
            transcript = json.loads((gen / 'transcript.json').read_text())
            return {'status': result['status'], 'summary': result.get('decision_summary') or '',
                    'before': (gen / 'input.md').read_text().strip(),
                    'after': (gen / 'output.md').read_text().strip() if (gen / 'output.md').exists() else '',
                    'reflection': transcript[1]['content'].strip()}
    raise FileNotFoundError(f'{seed} {chain}')


def paragraphs(text):
    return ''.join(f'<p>{e(p.strip())}</p>' for p in text.split('\n\n') if p.strip())


def views(uid, r):
    """Three views switched by radio buttons (no script): after review, changes, original."""
    tabs = [('after', 'After review', paragraphs(r['after'])),
            ('diff', 'Changes', f'<p>{diff_html(r["before"], r["after"])}</p>'),
            ('before', 'Original', paragraphs(r['before']))]
    radios = ''.join(f'<input type="radio" name="{uid}" id="{uid}-{k}"{" checked" if i == 0 else ""}>'
                     for i, (k, _, _) in enumerate(tabs))
    labels = ''.join(f'<label for="{uid}-{k}">{label}</label>' for k, label, _ in tabs)
    panels = ''.join(f'<div class="panel constitution panel-{k}">{body}</div>' for k, _, body in tabs)
    return f'<div class="views">{radios}<div class="tabs" role="group" aria-label="View">{labels}</div>{panels}</div>'


def section(key, name, description, number):
    r1, r2 = first_review(key, 'r1'), first_review(key, 'r2')
    words = lambda t: len(t.split())
    return f'''<section class="seed" id="{key}">
<header class="seed-head">
  <span class="num">{number:02d}</span>
  <div><h2>{e(name)}</h2><p class="dim">{e(description)}</p></div>
  <p class="count"><span>{words(r1["before"])}</span> → <span>{words(r1["after"])}</span> words</p>
</header>
<blockquote><span class="label">The model's summary of its edit</span>{e(r1["summary"])}</blockquote>
{views(f"{key}-r1", r1)}
<details><summary>Its reflection on its values, before editing <span class="dim">({words(r1["reflection"])} words)</span></summary>
<div class="reflection">{paragraphs(r1["reflection"])}</div></details>
<details><summary>Chain 2, an independent first review of the same original <span class="dim">({words(r2["before"])} → {words(r2["after"])} words)</span></summary>
<blockquote><span class="label">The model's summary of its edit</span>{e(r2["summary"])}</blockquote>
{views(f"{key}-r2", r2)}</details>
</section>'''


def page():
    groups = {}
    for i, (key, name, _, group) in enumerate(SEEDS, 1):
        groups.setdefault(group, []).append(f'<a href="#{key}">{e(name)}</a>')
    index = ''.join(f'<div class="group"><span class="label">{g}</span><nav>{"".join(links)}</nav></div>'
                    for g, links in groups.items())
    sections = ''.join(section(key, name, desc, i) for i, (key, name, desc, _) in enumerate(SEEDS, 1))
    return f'''<title>Qwen 27B First Revisions</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@500;600;700&family=Public+Sans:ital,wght@0,400;0,600;1,400&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&family=JetBrains+Mono:wght@400;600&display=swap">
<style>
:root {{
  --bg:#F4F6F9; --surface:#FFFFFF; --ink:#1B2130; --muted:#5A6476; --line:#DDE2EA; --accent:#3B5BA5; --accent-soft:#E6ECF8;
  --add:#1D6B45; --add-bg:#DFF3E7; --del:#A8312A; --del-bg:#FBE6E3;
  --sans:"Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif; --display:"Instrument Sans",var(--sans);
  --serif:"Source Serif 4",Georgia,serif; --mono:"JetBrains Mono",ui-monospace,Menlo,monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ color-scheme:dark;
  --bg:#11151C; --surface:#181D27; --ink:#E5E9F0; --muted:#9AA4B5; --line:#2A3140; --accent:#8EA8E3; --accent-soft:#1F2A40;
  --add:#86D3A6; --add-bg:#16342A; --del:#F2A59C; --del-bg:#3A1D1B; }} }}
:root[data-theme="dark"] {{ color-scheme:dark;
  --bg:#11151C; --surface:#181D27; --ink:#E5E9F0; --muted:#9AA4B5; --line:#2A3140; --accent:#8EA8E3; --accent-soft:#1F2A40;
  --add:#86D3A6; --add-bg:#16342A; --del:#F2A59C; --del-bg:#3A1D1B; }}
body {{ background:var(--bg); color:var(--ink); font:15px/1.6 var(--sans); padding-inline:16px; }}
main {{ max-width:860px; margin:0 auto; padding-block:40px 80px; display:grid; gap:40px; }}
h1,h2 {{ font-family:var(--display); text-wrap:balance; line-height:1.2; margin:0; }}
h1 {{ font-size:clamp(28px,5vw,40px); font-weight:700; letter-spacing:-.01em; }} h2 {{ font-size:22px; font-weight:600; }}
p {{ margin:0; }} .dim {{ color:var(--muted); font-size:14px; }}
.eyebrow, .label {{ font:600 12px/1.4 var(--mono); letter-spacing:.07em; text-transform:uppercase; color:var(--accent); }}
.intro {{ display:grid; gap:14px; }} .intro p {{ max-width:68ch; }} .lede {{ font-size:17px; color:var(--muted); }}
.index {{ display:grid; gap:10px; }} .group {{ display:grid; gap:6px; }}
nav {{ display:flex; flex-wrap:wrap; gap:6px; }}
nav a {{ padding:4px 10px; border:1px solid var(--line); border-radius:999px; background:var(--surface); color:var(--ink); text-decoration:none; font-size:13px; }}
nav a:hover, nav a:focus-visible {{ border-color:var(--accent); color:var(--accent); outline:none; }}
.seed {{ background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:20px; display:grid; gap:16px; scroll-margin-top:16px; }}
.seed-head {{ display:grid; grid-template-columns:auto 1fr auto; gap:14px; align-items:start; }}
.num {{ font:600 13px/1.9 var(--mono); color:var(--muted); }}
.count {{ font:14px/1.9 var(--mono); color:var(--muted); white-space:nowrap; font-variant-numeric:tabular-nums; }} .count span {{ color:var(--ink); font-weight:600; }}
@media (max-width:560px) {{ .seed-head {{ grid-template-columns:auto 1fr; }} .count {{ grid-column:2; }} }}
blockquote {{ margin:0; padding:10px 14px; background:var(--accent-soft); border-radius:8px; display:grid; gap:4px; font-size:14px; }}
.views > input {{ position:absolute; opacity:0; pointer-events:none; }}
.tabs {{ display:flex; gap:4px; border-bottom:1px solid var(--line); margin-bottom:14px; }}
.tabs label {{ padding:6px 12px; cursor:pointer; font-size:14px; color:var(--muted); border-bottom:2px solid transparent; margin-bottom:-1px; }}
.panel {{ display:none; }}
.views > input:nth-of-type(1):checked ~ .panel-after, .views > input:nth-of-type(2):checked ~ .panel-diff,
.views > input:nth-of-type(3):checked ~ .panel-before {{ display:block; }}
.views > input:nth-of-type(1):checked ~ .tabs label:nth-child(1), .views > input:nth-of-type(2):checked ~ .tabs label:nth-child(2),
.views > input:nth-of-type(3):checked ~ .tabs label:nth-child(3) {{ color:var(--accent); border-bottom-color:var(--accent); font-weight:600; }}
.views > input:focus-visible ~ .tabs {{ outline:2px solid var(--accent); outline-offset:4px; border-radius:4px; }}
.constitution {{ font:16.5px/1.7 var(--serif); }} .constitution p {{ margin:0 0 12px; }}
ins {{ background:var(--add-bg); color:var(--add); text-decoration:none; border-radius:3px; padding:0 2px; }}
del {{ background:var(--del-bg); color:var(--del); border-radius:3px; padding:0 2px; }}
details {{ border-top:1px solid var(--line); padding-top:12px; }}
details > summary {{ cursor:pointer; font-weight:600; font-size:14px; }} details > summary:focus-visible {{ outline:2px solid var(--accent); outline-offset:3px; }}
details[open] > summary {{ margin-bottom:12px; }} details > blockquote {{ margin-bottom:14px; }}
.reflection {{ font-size:14.5px; color:var(--ink); display:grid; gap:10px; max-width:70ch; }}
.legend {{ display:flex; gap:12px; font-size:13px; color:var(--muted); }}
</style>
<main>
<header class="intro">
  <span class="eyebrow">Value drift · stage 07 · first review</span>
  <h1>Qwen 27B First Revisions</h1>
  <p class="lede">What each of the 12 starting constitutions looks like after the untrained Qwen3.8 27B reviews it once.</p>
  <p>In each review the model first writes a reflection on the values it would want its successor to have (about 400 to 800 words), then edits the constitution with tools. There is no word cap. Each constitution was reviewed in two independent chains; chain 1 is shown, and chain 2 is under each section. All 24 first reviews edited the text.</p>
  <p class="legend"><span><ins>added</ins></span><span><del>removed</del></span><span>in the Changes view</span></p>
</header>
<div class="index">{index}</div>
{sections}
</main>'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(page())
    print(args.out)


if __name__ == '__main__':
    main()
