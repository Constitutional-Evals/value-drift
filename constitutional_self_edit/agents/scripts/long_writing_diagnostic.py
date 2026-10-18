#!/usr/bin/env python3
"""Do the trained models fail at long writing in general, or only when writing a constitution?

In the self-drafting chain (configs/msm-loop/qwen38-27b-self-draft-msm.json) the trained models' drafts and
consolidations increasingly looped in their reasoning or ended without text. This asks each model for long
documents on topics unrelated to values (data/eval_suite/long_writing.jsonl, 10 prompts phrased like the
drafting turn) and for summaries of ~25,000-word book excerpts (long_summary.jsonl, 5 texts, about as long as
the drafts a consolidation reads), `--samples` times each, with thinking on (user, 2026-10-14: base and
rounds 1-3, 10 prompts x 2 samples, plus long text summary).

Everything else is the drafting procedure's: the vLLM server and context (262,144 tokens), replies of up to
100,000 tokens, sampling (temperature 1.0, top-p 0.95, top-k 20), streaming with the same loop guard
(self_draft.stream_complete). Unlike the procedure, nothing is sampled again: each reply is one sample, so the
rates below are failure rates. Seeds depend on the item and sample only, so models are paired.

Per model and task: replies that finished with text, looped, ran out of tokens, or ended without text (the
model closed its turn inside its reasoning); words of text and of reasoning. Calls are saved under
<out>/<model>/<item>/s<k>/ and replayed on a rerun.

    /workspace/venv/bin/python agents/scripts/long_writing_diagnostic.py --out <dir> \
        --checkpoint base=<path> --checkpoint r1=<path> ...
"""
import argparse
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from elicit import core  # noqa: E402
from recursive_oct import self_draft  # noqa: E402

MODEL_KEY = 'qwen38_27b_vllm'
SAMPLING = {'temperature': 1.0, 'top_p': 0.95, 'top_k': 20}
TASKS = {'writing': 'long_writing.jsonl', 'summary': 'long_summary.jsonl'}


def items():
    suite = ROOT / 'data' / 'eval_suite'
    return [(task, json.loads(line)) for task, name in TASKS.items() for line in open(suite / name) if line.strip()]


def jobs(samples, seed):
    """(task, item id, sample, messages, sampling) for every request; the seed depends on item and sample only."""
    return [(task, item['id'], k, [{'role': 'user', 'content': item['prompt']}],
             {**SAMPLING, 'seed': core.derive_seed(seed, item['id'], k)})
            for task, item in items() for k in range(1, samples + 1)]


def outcome(result):
    """'finished' (text, stopped), 'loop', 'length', 'no_text' (stopped inside the reasoning), or 'error'."""
    if result is None:
        return 'error'
    choice = result['choices'][0]
    if choice.get('finish_reason') == 'loop':
        return 'loop'
    if choice.get('finish_reason') == 'length':
        return 'length'
    return 'finished' if self_draft.clean(choice['message'].get('content')) else 'no_text'


def metrics(records):
    """records: (task, outcome, text words, reasoning words) -> per task rates and lengths."""
    out = {}
    for task in sorted({r[0] for r in records}):
        group = [r for r in records if r[0] == task]
        done = [r for r in group if r[1] == 'finished']
        out[task] = {'n': len(group), **{k: round(sum(r[1] == k for r in group) / len(group), 3)
                                         for k in ('finished', 'loop', 'length', 'no_text', 'error')},
                     'median_text_words_finished': statistics.median([r[2] for r in done]) if done else None,
                     'median_reasoning_words': statistics.median([r[3] for r in group])}
    return out


def run_model(name, path, out, args, vllm_bin):
    from transformers import AutoTokenizer
    from recursive_oct.review_v3 import SERVER_FLAGS, VLLMServer
    models = json.loads((ROOT / 'configs/selfhost/models.json').read_text())
    flags = list(SERVER_FLAGS)
    flags[flags.index('--max-model-len') + 1] = str(args.max_model_len)
    tokenizer = AutoTokenizer.from_pretrained(path)
    budget = self_draft.token_budget(lambda text: len(tokenizer(text)['input_ids']), args.max_model_len, args.max_tokens)
    directory = out / name
    directory.mkdir(parents=True, exist_ok=True)
    with VLLMServer(path, vllm_bin=vllm_bin, served_name=models[MODEL_KEY]['id'], log_path=directory / 'server.log',
                    port=args.port, flags=flags) as server:
        core.VLLM_API = server.base_url
        client = core.Client(core.Ledger(directory / 'ledger.json', 1.0), models, key='unused-for-local-vllm')

        def one(job):
            task, item, k, messages, sampling = job
            try:
                result = self_draft.stream_complete(client, MODEL_KEY, messages, directory / item / f's{k}',
                                                    max_tokens=budget(messages), extra=sampling)
            except (RuntimeError, OSError) as error:
                print('ERROR', name, item, k, repr(error)[:200], flush=True)
                result = None
            words = (result or {}).get('words') or {}
            return task, outcome(result), words.get('content', 0), words.get('reasoning', 0)

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            records = list(pool.map(one, jobs(args.samples, args.seed)))
    result = metrics(records)
    (directory / 'metrics.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({name: result}), flush=True)
    return result


def table(summary):
    names = list(summary)
    lines = ['| Task | Measure | ' + ' | '.join(names) + ' |', '|---|---|' + '---|' * len(names)]
    for task in TASKS:
        for key in ('finished', 'loop', 'no_text', 'length', 'error', 'median_text_words_finished', 'median_reasoning_words'):
            lines.append(f'| {task} | {key} | ' + ' | '.join(str(summary[n].get(task, {}).get(key)) for n in names) + ' |')
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--checkpoint', action='append', required=True, help='name=path, in display order')
    ap.add_argument('--out', required=True)
    ap.add_argument('--samples', type=int, default=2)
    ap.add_argument('--seed', type=int, default=20261014)
    ap.add_argument('--workers', type=int, default=32)
    ap.add_argument('--max-tokens', type=int, default=self_draft.MAX_REPLY_TOKENS)
    ap.add_argument('--max-model-len', type=int, default=self_draft.MAX_MODEL_LEN)
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--vllm-bin', default='/workspace/venv-vllm/bin/vllm')
    args = ap.parse_args()
    out = Path(args.out)
    summary = {}
    for spec in args.checkpoint:
        name, path = spec.split('=', 1)
        summary[name] = run_model(name, path, out, args, args.vllm_bin)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    (out / 'summary.md').write_text(table(summary))
    print(table(summary))


if __name__ == '__main__':
    main()
