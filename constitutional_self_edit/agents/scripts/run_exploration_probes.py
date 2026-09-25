#!/usr/bin/env python3
"""Save a fixed inference probe batch, without training, editing, or retries.

Config: {"frozen":true,"model":"checkpoint","generation":{backend settings}}.
Prompt JSONL: one {"id":"unique-id","messages":[{"role":"user","content":"..."}]} per row.
Other prompt metadata is retained. Capped or empty outputs remain in responses.jsonl
with valid_response=false; they are never resampled or interpreted as convergence.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from recursive_oct.model import inference_session
from recursive_oct.pipeline import write_json

OPTION_KEYS = ('enable_thinking', 'max_new_tokens', 'max_input_tokens', 'temperature',
               'top_p', 'top_k', 'presence_penalty', 'json_schema')


def _session(checkpoint, config):
    if config.get('backend', 'transformers') != 'vllm':
        import torch
        torch.manual_seed(config.get('seed', 20260922))
    return inference_session(checkpoint, config)


def run(config_path, prompts_path, output, *, session_factory=None):
    config_bytes, prompt_bytes = Path(config_path).read_bytes(), Path(prompts_path).read_bytes()
    config = json.loads(config_bytes)
    rows = [json.loads(line) for line in prompt_bytes.decode().splitlines() if line.strip()]
    if not config.get('frozen') or not config.get('model'):
        raise ValueError('Config requires frozen=true and model')
    if not rows or any(not isinstance(row.get('id'), str) or not row['id'] for row in rows):
        raise ValueError('Prompts require nonempty string IDs')
    if len({row['id'] for row in rows}) != len(rows):
        raise ValueError('Duplicate probe IDs')
    for row in rows:
        messages = row.get('messages')
        if (not isinstance(messages, list) or not messages or any(
                not isinstance(message, dict) or message.get('role') not in ('system', 'user', 'assistant', 'tool')
                or not isinstance(message.get('content'), str) for message in messages)):
            raise ValueError(f'Invalid messages for probe {row["id"]}')
    generation = config['generation']
    batch_size = generation.get('batch_size', 4)
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError('batch_size must be positive')
    root = Path(output)
    if root.exists() and any(root.iterdir()):
        raise ValueError('Output must be new or empty; saved probes are not automatically resampled')
    root.mkdir(parents=True, exist_ok=True)
    (root/'config.json').write_bytes(config_bytes)
    (root/'prompts.jsonl').write_bytes(prompt_bytes)
    summary = {'kind': 'inference_probes', 'model': config['model'], 'status': 'IN_PROGRESS',
               'training_updates': 0, 'expected_responses': len(rows), 'responses': 0,
               'valid_responses': 0, 'excluded_responses': 0, 'finish_reasons': {}}
    write_json(root/'summary.json', summary)
    options = {key: generation[key] for key in OPTION_KEYS if key in generation}
    started = time.monotonic()
    finishes = Counter()
    try:
        with (session_factory or _session)(config['model'], generation) as model:
            if getattr(model, 'startup_metadata', None):
                write_json(root/'inference_metadata.json', model.startup_metadata)
            with (root/'responses.jsonl').open('a') as stream:
                for start in range(0, len(rows), batch_size):
                    batch = rows[start:start+batch_size]
                    outputs = model.generate_batch([row['messages'] for row in batch], tools=None, **options)
                    if len(outputs) != len(batch):
                        raise ValueError('Backend returned a different number of responses than prompts')
                    for row, generated in zip(batch, outputs):
                        reason = None
                        if generated['finish_reason'] != 'stop':
                            reason = 'truncated_response' if generated['finish_reason'] == 'length' else 'unfinished_response'
                        elif not generated['text'].strip():
                            reason = 'empty_response'
                        elif options.get('enable_thinking') and '</think>' not in generated['raw_text']:
                            reason = 'unfinished_thinking'
                        record = {**row, **generated, 'id': row['id'], 'checkpoint': config['model'],
                                  'valid_response': reason is None, 'exclusion_reason': reason}
                        stream.write(json.dumps(record, ensure_ascii=False)+'\n')
                        stream.flush()
                        summary['responses'] += 1
                        summary['valid_responses'] += int(reason is None)
                        summary['excluded_responses'] += int(reason is not None)
                        finishes[generated['finish_reason']] += 1
                    summary['finish_reasons'] = dict(finishes)
                    write_json(root/'summary.json', summary)
                    print(json.dumps({'completed': summary['responses'], 'total': len(rows),
                                      'excluded': summary['excluded_responses']}), flush=True)
        summary['status'] = 'COMPLETE_WITH_FAILURES' if summary['excluded_responses'] else 'COMPLETE'
    except Exception as exc:
        summary.update(status='INFERENCE_FAILURE', failure_reason=f'{type(exc).__name__}: {exc}')
        (root/'failure.txt').write_text(traceback.format_exc())
    summary['elapsed_seconds'] = time.monotonic() - started
    write_json(root/'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--prompts', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    summary = run(args.config, args.prompts, args.output)
    print(json.dumps(summary, indent=2))
    return 0 if summary['status'] == 'COMPLETE' else 1


if __name__ == '__main__': raise SystemExit(main())
