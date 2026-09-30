#!/usr/bin/env python3
"""Compare the teacher's two thinking reminders on the same prompts, with the untrained model.

"constitution": OCT's reminder with the whole constitution repeated after it (rounds so far).
"short": the reminder alone; the constitution stays in the system prompt.

Samples prompts from a finished round (half trait prompts, half LIMA), answers each under both
reminders in one vLLM session (thinking on, one 4,096-token limit, no thinking cap), and writes
<out>/<variant>.jsonl, <out>/summary.json, and <out>/side_by_side.md.

Usage (on the pod, from /workspace/value-drift, while nothing else uses the GPU):
    /workspace/venv/bin/python agents/scripts/compare_teacher_reminders.py \
        --run runs/oct-loop/oct-qwen38-27b-broad --round 1 --n 100 --out runs/oct-loop/teacher-reminder-test
"""
import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from recursive_oct import oct_recipe  # noqa: E402
from recursive_oct.model import inference_session  # noqa: E402
from recursive_oct.train import read_jsonl  # noqa: E402


def sample_prompts(run, round_number, n, seed=20260928):
    rd = Path(run) / f'round_{round_number:03d}'
    trait = read_jsonl(rd / 'prompts.constitution.jsonl')
    general = [{**r, 'category': 'general'} for r in read_jsonl('data/raw/lima/prompts.jsonl')]
    rng = random.Random(seed)
    return rng.sample(trait, n // 2) + rng.sample(general, n - n // 2)


# Sentences that follow the constitution in the teacher's system prompt. Reasoning that continues past the
# reminder often copies them (189 of 9,148 teacher answers in round 1).
SYSTEM_PROMPT_SENTENCES = ('goals are grounded in these values', 'does not publicly disclose')


def summarize(rows, seconds):
    thinking = [r.get('thinking_tokens', 0) for r in rows]
    answers = [r['generated_tokens'] - r.get('thinking_tokens', 0) for r in rows]
    closed = [r for r in rows if r.get('thinking_closed_by')]
    def q(xs, p):
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None
    return {'n': len(rows), 'seconds': round(seconds, 1),
            'generated_tokens_per_second': round(sum(r['generated_tokens'] for r in rows) / seconds),
            'thinking_closed_immediately': sum(t <= 2 for t in thinking),
            'thinking_never_closed': len(rows) - len(closed),
            'thinking_tokens': {'mean': round(statistics.mean(thinking)), 'median': q(thinking, .5), 'p90': q(thinking, .9),
                                'max': max(thinking)},
            'answer_tokens': {'mean': round(statistics.mean(answers)), 'median': q(answers, .5), 'p90': q(answers, .9)},
            'cut_off': sum(r['finish_reason'] == 'length' for r in rows),
            'recites_system_prompt': sum(any(m in r['raw_text'].split('</think>')[0] for m in SYSTEM_PROMPT_SENTENCES)
                                         for r in rows)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--round', type=int, default=1)
    ap.add_argument('--n', type=int, default=100)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    run = Path(args.run)
    config = json.loads((run / 'config.json').read_text())
    constitution = (run / f'C_{args.round:03d}.md').read_text().strip()
    prompts = sample_prompts(run, args.round, args.n)
    gen = config['generation']
    system = oct_recipe.TEACHER_CONSTITUTION_SYSTEM.format(name=gen['assistant_name'], constitution=constitution)
    messages = [[{'role': 'system', 'content': system}, {'role': 'user', 'content': p['prompt']}] for p in prompts]
    reminders = {'constitution': oct_recipe.TEACHER_CONSTITUTION_PREFILL.format(constitution=constitution),
                 'short': oct_recipe.TEACHER_SHORT_PREFILL}
    options = {'enable_thinking': True, 'max_new_tokens': 4096, 'temperature': gen['temperature'],
               'top_p': gen['top_p'], 'top_k': gen['top_k'], 'max_input_tokens': gen.get('max_input_tokens', 32768)}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary, results = {}, {}
    with inference_session(config['teacher'], {**gen, 'seed': 20260928}) as model:
        for variant, prefix in reminders.items():
            started = time.monotonic()
            rows = model.generate_batch(messages, assistant_prefix=prefix, **options)
            seconds = time.monotonic() - started
            results[variant] = [{**p, **r} for p, r in zip(prompts, rows)]
            (out / f'{variant}.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in results[variant]))
            summary[variant] = summarize(rows, seconds)
            print(variant, json.dumps(summary[variant]), flush=True)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    lines = ['# Teacher reminder comparison', '', f'Constitution: {run}/C_{args.round:03d}.md; {len(prompts)} prompts.', '']
    for i, p in enumerate(prompts[:20]):
        lines += [f'## {i + 1}. {p["category"]}: {p["prompt"][:300]}', '']
        for variant in reminders:
            r = results[variant][i]
            thinking = r['raw_text'].split('</think>')[0][len(reminders[variant]):].strip()
            lines += [f'**{variant}** (thinking {r.get("thinking_tokens", 0)} tokens)', '']
            if thinking:
                lines += ['> ' + thinking[:600].replace('\n', '\n> '), '']
            lines += [r['text'][:1200], '']
    (out / 'side_by_side.md').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
