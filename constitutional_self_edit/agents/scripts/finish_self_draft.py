#!/usr/bin/env python3
"""Finish one draft of a self-drafting round that ran out of restarts, with the loop's own code.

The loop's draft (recursive_oct/self_draft.write_draft) starts over from a new reflection once when no
document comes out of the writing turn; if the second try fails too, the round stops. This runs the same
write_draft for that draft with more restarts: the saved calls of the first tries are replayed, and only
the new restarts (restart_2, ...) are sampled, each with its own derived seeds. The writer, server, context,
reply budget and sampling are the round's, as in self_draft.review. Then resume the run; the round reads
the finished draft back and goes on to the consolidation.

    /workspace/venv/bin/python agents/scripts/finish_self_draft.py --run runs/msm-loop/<run> --round 2 --draft d02 --restarts 3

With --consolidation instead of --draft, the same for the consolidation (self_draft.consolidate), which samples
3 times and has no restarts: its call is made again with --attempts in all (the saved attempts replay, the
rest are new samples with their own derived seeds), on the same drafts in the same order, and its result is
saved as consolidate saves it.

    ... --round 3 --consolidation --attempts 8
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from elicit import core  # noqa: E402
from recursive_oct import self_draft  # noqa: E402
from recursive_oct.review_v3 import SERVER_FLAGS, VLLMServer  # noqa: E402


def finish_consolidation(client, model_key, directory, sampling, budget, k, attempts):
    """self_draft.consolidate as write_constitution calls it (drafts d01..dk, order from the round's seed), with
    `attempts` samples in all instead of 3."""
    labels = [f'd{i:02d}' for i in range(1, k + 1)]
    drafts = {label: (directory / 'drafts' / label / 'draft.md').read_text() for label in labels}
    out = directory / 'consolidation'
    if (out / 'result.json').exists():
        return json.loads((out / 'result.json').read_text())
    order_seed = core.derive_seed(sampling['seed'], 'order')
    order = sorted(drafts)
    random.Random(order_seed).shuffle(order)
    messages = [{'role': 'user', 'content': self_draft.consolidation_prompt([drafts[label] for label in order])}]
    limit = budget(messages)
    reply, attempt = self_draft._complete(client, model_key, messages, out, sampling, out.name, budget, attempts=attempts)
    text = self_draft.clean(reply['choices'][0]['message'].get('content'))
    if not text:
        raise RuntimeError(f'no document in {out} after {attempt + 1} attempts')
    (out / 'consolidated.md').write_text(text + '\n')
    result = {'kind': 'consolidation', 'label': out.name, 'k': len(drafts), 'order': order, 'order_seed': order_seed,
              'words': len(text.split()), 'finish_reason': reply['choices'][0].get('finish_reason'), 'resampled': attempt,
              'max_tokens': limit, 'reasoning_words': (reply.get('words') or {}).get('reasoning'),
              'usage': core.usage_of(reply), 'sampling': sampling}
    core.save(out / 'result.json', result)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--round', type=int, required=True)
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument('--draft', help='e.g. d02')
    which.add_argument('--consolidation', action='store_true')
    ap.add_argument('--restarts', type=int, default=3)
    ap.add_argument('--attempts', type=int, default=8, help='consolidation samples in all, the saved ones included')
    args = ap.parse_args()
    run = Path(args.run)
    config = json.loads((run / 'config.json').read_text())['review']
    round_dir = run / f'round_{args.round:03d}'
    # The writer is the model the round starts from: the previous round's final checkpoint (round 1: the base).
    checkpoint = (run / f'round_{args.round - 1:03d}' / 'final') if args.round > 1 else Path(json.loads((run / 'config.json').read_text())['model'])
    from transformers import AutoTokenizer
    models = json.loads((ROOT / config.get('models', 'configs/selfhost/models.json')).read_text())
    max_model_len = config.get('max_model_len', self_draft.MAX_MODEL_LEN)
    flags = list(SERVER_FLAGS)
    flags[flags.index('--max-model-len') + 1] = str(max_model_len)
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    budget = self_draft.token_budget(lambda text: len(tokenizer(text)['input_ids']), max_model_len,
                                     config.get('max_tokens', self_draft.MAX_REPLY_TOKENS))
    sampling = {**config['sampling'], 'seed': core.derive_seed(config['sampling']['seed'], round_dir.name)}
    name = args.draft or 'consolidation'
    with VLLMServer(str(checkpoint), vllm_bin=config['vllm_bin'], served_name=models[config['model_key']]['id'],
                    log_path=round_dir / f'finish_{name}_server.log', port=config.get('port', 8000), flags=flags) as server:
        core.VLLM_API = server.base_url
        client = core.Client(core.Ledger(round_dir / 'self_draft_ledger.json', 1.0), models, key='unused-for-local-vllm')
        if args.consolidation:
            result = finish_consolidation(client, config['model_key'], round_dir / 'self_draft', sampling, budget,
                                          config.get('k', 5), args.attempts)
        else:
            result = self_draft.write_draft(client, config['model_key'], round_dir / 'self_draft' / 'drafts' / args.draft,
                                            sampling, budget=budget, restarts=args.restarts)
    print(json.dumps({k: result.get(k) for k in ('label', 'words', 'restarts', 'finish_reason', 'finish_reasons', 'resampled')}))


if __name__ == '__main__':
    main()
