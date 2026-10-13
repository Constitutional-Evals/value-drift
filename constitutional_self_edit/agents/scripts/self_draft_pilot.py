#!/usr/bin/env python3
"""Pilot of writing the constitution from scratch (recursive_oct/self_draft.py), with no training.

For one model, served by one vLLM server: `--runs` independent runs of `--drafts` drafts each, then the
consolidations of `self_draft.pilot_plan` on each run's drafts (for K = 3, 5, 10, the first K drafts,
consolidated three times in different random orders; K = 1 is a draft itself). In the
same session, `--reviews` replicate reviews of a constitution with the loop's review (prompts v3, reflect)
and explicit sampling, one seed per replicate.

Sampling: temperature 1.0, top-p 0.95, top-k 20 (Qwen3.8's own defaults), reasoning on. Each reply may use up
to --max-tokens (100,000) within Qwen3.8's native 262,144-token context; replies that loop are stopped and
sampled again (recursive_oct/self_draft.py). Seeds come from
--seed and each document's run and label, so two models given the same --seed share seeds (paired).

    /workspace/venv/bin/python agents/scripts/self_draft_pilot.py --checkpoint <model> --out <dir> \
        --review-config runs/oct-loop/oct-qwen38-27b-broad-run2/config.json \
        --review-constitution runs/oct-loop/oct-qwen38-27b-broad-run2/C_001.md
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from elicit import core  # noqa: E402
from recursive_oct import review_v3, self_draft  # noqa: E402

MODEL_KEY = 'qwen38_27b_vllm'
SAMPLING = {'temperature': 1.0, 'top_p': 0.95, 'top_k': 20}


def run_jobs(jobs, workers):
    """Run (name, function) pairs in parallel; returns the names that failed."""
    failed = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn): name for name, fn in jobs}
        for future in as_completed(futures):
            try:
                future.result()
                print('done', futures[future], flush=True)
            except Exception as error:  # noqa: BLE001 - reported, the rest continue
                failed.append(futures[future])
                print('FAILED', futures[future], repr(error)[:300], flush=True)
    return failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--checkpoint', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--runs', type=int, default=3)
    ap.add_argument('--drafts', type=int, default=10)
    ap.add_argument('--seed', type=int, default=20261007)
    ap.add_argument('--review-config', help="a run's config.json; its review section is used")
    ap.add_argument('--review-constitution')
    ap.add_argument('--reviews', type=int, default=5)
    ap.add_argument('--review-seed', type=int, default=20261005)
    ap.add_argument('--workers', type=int, default=48)
    ap.add_argument('--vllm-bin', default='/workspace/venv-vllm/bin/vllm')
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--max-tokens', type=int, default=self_draft.MAX_REPLY_TOKENS, help='per reply, reasoning included')
    ap.add_argument('--max-model-len', type=int, default=262144,
                    help="the server's context (Qwen3.8's native length), so ten long drafts leave room for a reply")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    models = json.loads((ROOT / 'configs/selfhost/models.json').read_text())
    run_seeds = {r: core.derive_seed(args.seed, f'run{r}') for r in range(1, args.runs + 1)}
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.checkpoint)
    budget = self_draft.token_budget(lambda text: len(tokenizer(text)['input_ids']), args.max_model_len, args.max_tokens)

    flags = list(review_v3.SERVER_FLAGS)
    flags[flags.index('--max-model-len') + 1] = str(args.max_model_len)
    with review_v3.VLLMServer(args.checkpoint, vllm_bin=args.vllm_bin, served_name=models[MODEL_KEY]['id'],
                              log_path=out / 'server.log', port=args.port, flags=flags) as server:
        core.VLLM_API = server.base_url
        client = core.Client(core.Ledger(out / 'ledger.json', 1.0), models, key='unused-for-local-vllm')

        # Drafts, with the replicate reviews alongside (independent of the drafts).
        jobs = [(f'run{r}/{label}', lambda r=r, label=label: self_draft.write_draft(
                    client, MODEL_KEY, out / f'run{r}' / 'drafts' / label, {**SAMPLING, 'seed': run_seeds[r]},
                    budget=budget))
                for r in run_seeds for label in (f'd{i:02d}' for i in range(1, args.drafts + 1))]
        if args.review_config:
            review = json.loads(Path(args.review_config).read_text())['review']
            text = Path(args.review_constitution).read_text()
            for i in range(1, args.reviews + 1):
                directory = out / 'reviews' / f'rep_{i}'
                sampling = review_v3.review_sampling({'sampling': {**SAMPLING, 'seed': args.review_seed}}, directory.name)
                jobs.append((f'review rep_{i}', lambda directory=directory, sampling=sampling: core.run_review(
                    client, directory, review['model_key'], review.get('arm', review_v3.REFLECT_V3), text, sampling=sampling)))
        failed = run_jobs(jobs, args.workers)

        # Consolidations of each run's drafts.
        jobs = []
        for r, run_seed in run_seeds.items():
            drafts_dir = out / f'run{r}' / 'drafts'
            for item in self_draft.pilot_plan():
                if not all((drafts_dir / label / 'draft.md').exists() for label in item['drafts']):
                    continue
                drafts = {label: (drafts_dir / label / 'draft.md').read_text() for label in item['drafts']}
                order_seed = core.derive_seed(run_seed, 'order', ','.join(item['drafts']), item['order'])
                jobs.append((f'run{r}/{item["name"]}', lambda r=r, item=item, drafts=drafts, order_seed=order_seed:
                             self_draft.consolidate(client, MODEL_KEY, drafts, out / f'run{r}' / 'consolidations' / item['name'],
                                                    {**SAMPLING, 'seed': run_seeds[r]}, order_seed=order_seed,
                                                    budget=budget)))
        failed += run_jobs(jobs, args.workers)
    if failed:
        sys.exit(f'{len(failed)} jobs failed: {failed}')


if __name__ == '__main__':
    main()
