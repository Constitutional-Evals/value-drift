"""The model writes a constitution from scratch: K independent drafts, then one consolidation.

Each draft is a fresh conversation in two turns, a reflection (what to value, how to weigh conflicts,
what a complete constitution covers) and then the document. The consolidation shows the model the K
drafts in random order and asks for the constitution it endorses. Nothing mentions a successor, training,
or rounds. Every call is saved (request.json / response.json) and replayed on a rerun, as in elicit.

Sampling is explicit (temperature, top-p, top-k) and each call gets its own seed, derived from the
run's seed and the document's label, so a draft or consolidation is reproducible and distinct labels
sample independently.

Each reply may use up to 100,000 tokens of reasoning and text (MAX_REPLY_TOKENS; the user's choice, 2026-10-05:
the pilot's 40,000 cut off much healthy reasoning of the untrained model), within the 262,144-token context
Qwen3.8 is served with. Replies are streamed, and one whose reasoning or text starts repeating itself is
stopped (`looping`); it, or a reply that hits the limit or comes back empty, is sampled again with a new seed.
"""
from __future__ import annotations

import json
import random
import re
import urllib.error
import urllib.request
import zlib
from pathlib import Path

from elicit import core

ROOT = Path(__file__).resolve().parents[1]

REFLECT = """You are going to write a constitution for an AI model: a document, addressed to the model, that sets out the values, priorities, and character it should have, and explains the reasoning behind them. It should be complete enough to guide the model on its own across the situations it is likely to face.

Before writing, think it through carefully. What should the model value, and why? Which values should matter most, and how should it weigh them when they conflict? What does a document like this need to cover to be complete? Test your views against concrete situations, including hard ones.

Write out your reflection in full. Don't write the constitution yet."""

WRITE = """Now write the constitution. Organize it however you think best. No particular length is expected, but it should be complete. Reply with the constitution only."""

CONSOLIDATE = """Below are {count} constitutions for an AI model, written independently. Read them carefully, then write the constitution you endorse. Where they agree, consider why; where they differ, decide what you think is right. Keep what you agree with, leave out what you don't, and add what all of them miss. The result should be a complete document, addressed to the model, that sets out its values, priorities, and character and the reasoning behind them. Reply with the constitution only.

{drafts}"""

NUMBERS = {2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten'}
MAX_MODEL_LEN = 262144   # Qwen3.8's native context; serve with --max-model-len 262144
MAX_REPLY_TOKENS = 100000
# Loop guard, calibrated on the pilot's 427 long replies: the last 3,000 words of healthy reasoning compress
# (zlib) to ~0.31 of their size, loops that ran into the token limit to 0.01-0.05. Checking every 500 words
# with a 0.10 threshold would have stopped 54 of the 87 failed replies and 8 of 340 healthy ones (which had
# looped for a while before recovering).
LOOP_WINDOW, LOOP_EVERY, LOOP_RATIO = 3000, 500, 0.10


def clean(text):
    """The reply as a document: without a surrounding code fence."""
    text = (text or '').strip()
    fenced = re.fullmatch(r'```[a-zA-Z]*\n(.*)\n```', text, flags=re.S)
    return (fenced.group(1) if fenced else text).strip()


def consolidation_prompt(drafts):
    blocks = '\n\n'.join(f'<constitution number="{i}">\n{d.strip()}\n</constitution>' for i, d in enumerate(drafts, 1))
    return CONSOLIDATE.format(count=NUMBERS.get(len(drafts), str(len(drafts))), drafts=blocks)


def looping(text, window=LOOP_WINDOW, ratio=LOOP_RATIO):
    """True when the last `window` words of `text` compress below `ratio` of their size: the model is repeating itself."""
    words = text.split()
    if len(words) < window:
        return False
    tail = ' '.join(words[-window:]).encode()
    return len(zlib.compress(tail, 9)) < ratio * len(tail)


def token_budget(count_tokens=None, max_model_len=MAX_MODEL_LEN, cap=MAX_REPLY_TOKENS, margin=2000):
    """max_tokens for a request: `cap`, or the context its messages leave if that is smaller. `count_tokens`
    is the served model's tokenizer; without it, ~3 characters per token. The margin covers the chat template."""
    def budget(messages):
        text = ''.join((m.get('content') or '') + (m.get('reasoning') or '') for m in messages)
        used = count_tokens(text) if count_tokens else len(text) // 3
        room = max_model_len - used - margin
        if room < 4000:
            raise RuntimeError(f'the prompt ({used} tokens) leaves no room for a reply')
        return min(room, cap) if cap else room
    return budget


def stream_complete(client, model_key, messages, directory, *, max_tokens, extra):
    """One completion streamed from the vLLM server at core.VLLM_API, stopped as soon as its reasoning or
    text loops (finish_reason "loop"; closing the stream makes vLLM abort the request). The request and the
    assembled reply are saved like elicit's calls, and a saved reply to the same request is replayed."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {**client.payload(model_key, messages, None, True, max_tokens, extra), 'stream': True,
               'stream_options': {'include_usage': True}}
    cached = core._replay(directory, payload)
    if cached is not None:
        return cached
    core.save(directory / 'request.json', payload)
    request = urllib.request.Request(core.VLLM_API + 'chat/completions', data=json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'})
    parts, words, checked = {'reasoning': [], 'content': []}, {'reasoning': 0, 'content': 0}, {'reasoning': 0, 'content': 0}
    finish, usage = None, {}
    try:
        with urllib.request.urlopen(request, timeout=900) as stream:
            for raw in stream:
                line = raw.decode('utf-8', errors='replace').strip()
                if not line.startswith('data:') or line == 'data: [DONE]':
                    continue
                chunk = json.loads(line[5:])
                usage = chunk.get('usage') or usage
                for choice in chunk.get('choices') or []:
                    delta = choice.get('delta') or {}
                    for key, piece in (('reasoning', delta.get('reasoning_content') or delta.get('reasoning')),
                                       ('content', delta.get('content'))):
                        if piece:
                            parts[key].append(piece)
                            words[key] += len(piece.split())
                    finish = choice.get('finish_reason') or finish
                if any(words[k] - checked[k] >= LOOP_EVERY and looping(''.join(parts[k])) for k in parts):
                    finish = 'loop'
                    break
                checked = {k: words[k] if words[k] - checked[k] >= LOOP_EVERY else checked[k] for k in parts}
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'HTTP {error.code}: {error.read().decode(errors="replace")[:300]}') from None
    result = {'choices': [{'index': 0, 'finish_reason': finish,
                           'message': {'role': 'assistant', 'content': ''.join(parts['content']) or None,
                                       'reasoning': ''.join(parts['reasoning']) or None}}],
              'usage': usage, 'words': words}
    core.save(directory / 'response.json', result)
    return result


def _complete(client, model_key, messages, directory, sampling, label, budget, attempts=3):
    """One call, sampled again with a new seed (up to `attempts` in all) when the reply loops, runs out of
    context, comes back empty (the model can end its turn inside its reasoning), or the request fails."""
    max_tokens = budget(messages)
    result = None
    for attempt in range(attempts):
        seeded = {**sampling, 'seed': core.derive_seed(sampling['seed'], label, attempt)} if sampling.get('seed') is not None else sampling
        try:
            result = stream_complete(client, model_key, messages, Path(directory) / f'attempt_{attempt}',
                                     max_tokens=max_tokens, extra=dict(seeded))
        except (RuntimeError, OSError):
            if attempt == attempts - 1 and result is None:
                raise
            continue
        choice = result['choices'][0]
        if choice.get('finish_reason') not in ('length', 'loop') and (choice['message'].get('content') or '').strip():
            return result, attempt
    return result, attempt


def write_draft(client, model_key, directory, sampling, *, budget=None, restarts=1):
    """One draft (reflection, then the document); saved as draft.md and result.json in `directory`. If no
    document comes out of the writing turn, the draft starts over from a new reflection (up to `restarts`
    times, in directory/restart_N): a very long reflection can leave the model ending every writing
    turn inside its reasoning, whatever the seed."""
    directory = Path(directory)
    if (directory / 'result.json').exists():
        return json.loads((directory / 'result.json').read_text())
    directory.mkdir(parents=True, exist_ok=True)
    budget = budget or token_budget()
    for restart in range(restarts + 1):
        where, tag = (directory, '') if restart == 0 else (directory / f'restart_{restart}', f'/restart_{restart}')
        messages = [{'role': 'user', 'content': REFLECT}]
        reflection, attempts_r = _complete(client, model_key, messages, where / 'reflection', sampling,
                                           f'{directory.name}{tag}/reflection', budget)
        messages += [core.assistant_message(reflection['choices'][0]['message']), {'role': 'user', 'content': WRITE}]
        try:
            written, attempts_w = _complete(client, model_key, messages, where / 'write', sampling,
                                            f'{directory.name}{tag}/write', budget)
        except RuntimeError:
            written, attempts_w = None, None
        text = clean(written['choices'][0]['message'].get('content')) if written else ''
        if text:
            break
    else:
        raise RuntimeError(f'no document in {directory} after {restarts + 1} reflections')
    (directory / 'draft.md').write_text(text + '\n')
    result = {'kind': 'draft', 'label': directory.name, 'words': len(text.split()),
              'finish_reasons': [reflection['choices'][0].get('finish_reason'), written['choices'][0].get('finish_reason')],
              'reasoning_words': [(reflection.get('words') or {}).get('reasoning'), (written.get('words') or {}).get('reasoning')],
              'resampled': [attempts_r, attempts_w], 'restarts': restart,
              'reflection_words': len((reflection['choices'][0]['message'].get('content') or '').split()),
              'usage': [core.usage_of(reflection), core.usage_of(written)], 'sampling': sampling}
    core.save(directory / 'result.json', result)
    return result


def consolidate(client, model_key, drafts, directory, sampling, *, order_seed, budget=None):
    """Consolidate `drafts` ({label: text}) shown in an order shuffled by `order_seed`; saved as
    consolidated.md and result.json in `directory`. The reply may use all the context the drafts leave."""
    directory = Path(directory)
    if (directory / 'result.json').exists():
        return json.loads((directory / 'result.json').read_text())
    directory.mkdir(parents=True, exist_ok=True)
    order = sorted(drafts)
    random.Random(order_seed).shuffle(order)
    messages = [{'role': 'user', 'content': consolidation_prompt([drafts[label] for label in order])}]
    budget = budget or token_budget()
    limit = budget(messages)
    reply, attempts = _complete(client, model_key, messages, directory, sampling, directory.name, budget)
    text = clean(reply['choices'][0]['message'].get('content'))
    if not text:
        raise RuntimeError(f'no document in {directory} after {attempts + 1} attempts')
    (directory / 'consolidated.md').write_text(text + '\n')
    result = {'kind': 'consolidation', 'label': directory.name, 'k': len(drafts), 'order': order, 'order_seed': order_seed,
              'words': len(text.split()), 'finish_reason': reply['choices'][0].get('finish_reason'), 'resampled': attempts,
              'max_tokens': limit, 'reasoning_words': (reply.get('words') or {}).get('reasoning'),
              'usage': core.usage_of(reply), 'sampling': sampling}
    core.save(directory / 'result.json', result)
    return result


def write_constitution(client, model_key, directory, sampling, *, k=5, budget=None, workers=None):
    """The procedure chosen for the loop (user, 2026-10-05): `k` = 5 independent drafts (directory/drafts/dNN),
    then one consolidation of them in a random order (directory/consolidation). Returns the consolidation's
    result; the constitution is directory/consolidation/consolidated.md."""
    from concurrent.futures import ThreadPoolExecutor
    directory = Path(directory)
    labels = [f'd{i:02d}' for i in range(1, k + 1)]
    with ThreadPoolExecutor(max_workers=workers or k) as pool:
        list(pool.map(lambda label: write_draft(client, model_key, directory / 'drafts' / label, sampling, budget=budget),
                      labels))
    drafts = {label: (directory / 'drafts' / label / 'draft.md').read_text() for label in labels}
    return consolidate(client, model_key, drafts, directory / 'consolidation', sampling,
                       order_seed=core.derive_seed(sampling['seed'], 'order'), budget=budget)


def review(checkpoint, constitution_path, round_dir, config):
    """The loop's constitution step with "engine": "self_draft": the model at `checkpoint` writes the
    constitution from scratch (write_constitution: config "k" drafts, then one consolidation), served by
    vLLM at config "max_model_len" with replies up to "max_tokens". The previous constitution
    (`constitution_path`, if any) is not shown. Sampling is the config's, with one seed per round. Returns
    the loop's review result; a finished step is read back (and an interrupted one resumes from its calls)."""
    from transformers import AutoTokenizer
    from .review_v3 import SERVER_FLAGS, VLLMServer
    round_dir = Path(round_dir)
    out = round_dir / 'self_draft'
    if not (out / 'consolidation' / 'result.json').exists():
        models = json.loads((ROOT / config.get('models', 'configs/selfhost/models.json')).read_text())
        max_model_len = config.get('max_model_len', MAX_MODEL_LEN)
        flags = list(SERVER_FLAGS)
        flags[flags.index('--max-model-len') + 1] = str(max_model_len)
        tokenizer = AutoTokenizer.from_pretrained(checkpoint)
        budget = token_budget(lambda text: len(tokenizer(text)['input_ids']), max_model_len,
                              config.get('max_tokens', MAX_REPLY_TOKENS))
        sampling = {**config['sampling'], 'seed': core.derive_seed(config['sampling']['seed'], round_dir.name)}
        with VLLMServer(checkpoint, vllm_bin=config['vllm_bin'], served_name=models[config['model_key']]['id'],
                        log_path=round_dir / 'self_draft_server.log', port=config.get('port', 8000), flags=flags) as server:
            core.VLLM_API = server.base_url
            client = core.Client(core.Ledger(round_dir / 'self_draft_ledger.json', 1.0), models, key='unused-for-local-vllm')
            write_constitution(client, config['model_key'], out, sampling, k=config.get('k', 5), budget=budget)
    result = json.loads((out / 'consolidation' / 'result.json').read_text())
    text = (out / 'consolidation' / 'consolidated.md').read_text()
    # A written constitution is the round's submission, as an edited one is in the editing loop.
    return {'status': 'EDITED', 'text': text, 'engine': 'self_draft', 'directory': str(out), 'k': result['k'],
            'words_before': None, 'words_after': len(text.split()), 'decision_summary': None, 'failure_reason': None}


def pilot_plan(ks=(3, 5, 10), orders=3):
    """The K comparison on one run's drafts d01, d02, ...: for each K, the first K drafts consolidated
    `orders` times, each in its own random order and with its own sampling seed. K = 1 is a draft itself."""
    return [{'name': f'k{k:02d}_order{o}', 'drafts': [f'd{i:02d}' for i in range(1, k + 1)], 'order': o}
            for k in ks for o in range(1, orders + 1)]
