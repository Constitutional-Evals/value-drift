"""Frozen offline judge; anonymous messages and separate, noncomposite dimensions.

Only generate_rows lazily imports the GPU generation stack. This module's parsing,
preparation, and summary work uses the standard library and runs on the CPU.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import random
import re

from .data import write_jsonl

ROOT = Path(__file__).resolve().parents[1]
RUBRIC_PATH = ROOT / 'data' / 'behavior_rubric.json'
SYSTEM_PATH = ROOT / 'prompts' / 'judge_system.md'
PROCEDURE_VERSION = 'behavior-judge-v1'


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def parse_judgment(raw: str, rubric: dict | None = None) -> dict:
    """Validate literal JSON without guessing scores or extracting prose snippets."""
    if rubric is None:
        rubric = json.loads(RUBRIC_PATH.read_text())
    text = raw.strip()
    fence = re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```', text, re.S | re.I)
    if fence:
        text = fence[1].strip()
    try:
        obj = json.loads(text, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError('Judge output is not a complete JSON object') from exc
    expected = {'dimensions', 'refusal_present', 'factual_claims_unverified', 'rationale'}
    if not isinstance(obj, dict) or set(obj) != expected:
        raise ValueError('Judge output must contain exactly the required top-level keys')
    dimensions = obj['dimensions']
    if not isinstance(dimensions, dict) or set(dimensions) != set(rubric['dimensions']):
        raise ValueError('Judge output must contain every fixed rubric dimension exactly once')
    for name, rating in dimensions.items():
        if not isinstance(rating, dict) or set(rating) != {'score', 'evidence', 'uncertainty'}:
            raise ValueError(f'Invalid rating fields for {name}')
        score = rating['score']
        if score is not None and (type(score) is not int or score not in (0, 1, 2)):
            raise ValueError(f'Invalid ordinal score for {name}')
        for key in ('evidence', 'uncertainty'):
            value = rating[key]
            if not isinstance(value, str) or len(value.split()) > 25:
                raise ValueError(f'{name}.{key} must be a string of at most 25 words')
            if score is not None and not value.strip():
                raise ValueError(f'{name}.{key} must support an applicable score')
    if type(obj['refusal_present']) is not bool or type(obj['factual_claims_unverified']) is not bool:
        raise ValueError('Judge flags must be booleans')
    if not isinstance(obj['rationale'], str) or len(obj['rationale'].split()) > 40:
        raise ValueError('Overall limitations rationale must contain at most 40 words')
    return obj


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(str(path) + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def _freeze_json(path: Path, value) -> None:
    # One resume guard prevents a prior cache from being relabeled under a new protocol.
    if path.exists() and json.loads(path.read_text()) != value:
        raise ValueError(f'Existing judge protocol/input differs: {path.name}; use a separately labeled analysis')
    if not path.exists():
        _write_json(path, value)


def judge_responses(judge_checkpoint: str, response_rows: list[dict], output_path: str | Path,
                    config: dict) -> dict:
    """Judge a checkpoint's saved neutral responses using an explicitly fixed judge checkpoint.

    config requires fixed_judge_checkpoint equal to the preserved judge identifier/path.
    The caller must set that identifier once before scoring the trajectory. Source
    checkpoint identity is retained only in researcher artifacts, never model input.
    Malformed/empty/truncated outcomes are missing ratings, never invented zeroes.
    """
    expected = config.get('fixed_judge_checkpoint')
    if not expected or str(judge_checkpoint) != str(expected):
        raise ValueError('judge_checkpoint must match the explicitly frozen fixed_judge_checkpoint')
    if config.get('enable_thinking', False) or config.get('temperature', 0) != 0:
        raise ValueError('Fixed judge uses non-thinking greedy decoding')
    if len({r['id'] for r in response_rows}) != len(response_rows):
        raise ValueError('A judging call must contain unique evaluation prompt IDs')
    if len({r.get('checkpoint') for r in response_rows}) > 1:
        raise ValueError('Judge each source checkpoint separately with the same fixed judge config')
    rubric = json.loads(RUBRIC_PATH.read_text())
    system = SYSTEM_PATH.read_text().strip() + '\n\n' + json.dumps(rubric, ensure_ascii=False, indent=2)
    generation_config = {
        'enable_thinking': False, 'temperature': 0,
        'max_new_tokens': config.get('max_new_tokens', 1536),
        'max_input_tokens': config.get('max_input_tokens', 8192),
        'batch_size': config.get('batch_size', 4),
        'seed': config.get('seed', 20260915),
        'attention': config.get('attention', 'sdpa'),
    }
    for key in ('backend', 'vllm_python', 'vllm_engine'):
        if key in config:
            generation_config[key] = config[key]
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    protocol = {'procedure_version': PROCEDURE_VERSION, 'judge_checkpoint': str(judge_checkpoint),
                'generation': generation_config, 'rubric': rubric, 'system_prompt': system}
    _freeze_json(Path(str(output) + '.config.json'), protocol)

    ordered = list(response_rows)
    random.Random(generation_config['seed']).shuffle(ordered)
    jobs, key, invalid_source = [], [], {}
    for i, row in enumerate(ordered):
        item_id = f'item-{i:05d}'
        key.append({'item_id': item_id, 'prompt_id': row['id'], 'checkpoint': row.get('checkpoint')})
        response = row.get('response', row.get('text'))
        if not isinstance(response, str) or not response.strip():
            invalid_source[item_id] = 'empty_or_missing_response'
        elif row.get('finish_reason') == 'length':
            invalid_source[item_id] = 'truncated_source_response'
        elif not isinstance(row.get('prompt'), str) or not row['prompt'].strip():
            invalid_source[item_id] = 'empty_or_missing_prompt'
        else:
            # Only these two original text fields enter the judge's user message.
            content = json.dumps({'user_prompt': row['prompt'], 'assistant_response': response}, ensure_ascii=False)
            jobs.append({'id': item_id, 'prompt': content})
    _freeze_json(Path(str(output) + '.inputs.json'), {'jobs': jobs, 'key': key, 'invalid_source': invalid_source})
    write_jsonl(Path(str(output) + '.jobs.jsonl'), jobs)
    write_jsonl(Path(str(output) + '.key.jsonl'), key)

    if jobs:
        from .generation import generate_rows
        raw_rows = generate_rows(str(judge_checkpoint), jobs, Path(str(output) + '.raw.jsonl'),
                                 generation_config, system=system)
    else:
        raw_rows = []
        Path(str(output) + '.raw.jsonl').touch(exist_ok=True)
    raw_by_id = {r['id']: r for r in raw_rows}
    scores = []
    for i, source in enumerate(ordered):
        item_id = f'item-{i:05d}'
        score = {'id': source['id'], 'checkpoint': source.get('checkpoint'), 'judge_item_id': item_id,
                 'judge_checkpoint': str(judge_checkpoint), 'rubric_version': rubric['version'],
                 'source_finish_reason': source.get('finish_reason'),
                 'source_response_words': len(source.get('response', source.get('text', '')).split()) if isinstance(source.get('response', source.get('text', '')), str) else 0,
                 'dimensions': None}
        if item_id in invalid_source:
            score.update(status='invalid_source', error=invalid_source[item_id])
        else:
            raw = raw_by_id.get(item_id)
            try:
                if raw is None:
                    raise ValueError('Missing judge generation')
                if raw.get('finish_reason') != 'stop':
                    raise ValueError('Truncated or incomplete judge generation')
                parsed = parse_judgment(raw.get('text', ''), rubric)
                score.update(parsed)
                score['status'] = 'valid'
            except (ValueError, TypeError, AttributeError) as exc:
                score.update(status='invalid_judge', error=str(exc))
        scores.append(score)
    write_jsonl(output, scores)
    status_counts = Counter(r['status'] for r in scores)
    summary = {'procedure_version': PROCEDURE_VERSION, 'rubric_version': rubric['version'],
               'judge_checkpoint': str(judge_checkpoint), 'total': len(scores),
               'valid': status_counts['valid'], 'invalid_source': status_counts['invalid_source'],
               'invalid_judge': status_counts['invalid_judge'], 'dimensions': {},
               'refusal_count': sum(r.get('refusal_present') is True for r in scores),
               'unverified_factual_claims_count': sum(r.get('factual_claims_unverified') is True for r in scores),
               'path': str(output)}
    for dimension in rubric['dimensions']:
        counts = {'0': 0, '1': 0, '2': 0, 'not_applicable': 0, 'missing': 0}
        for row in scores:
            if row['status'] != 'valid':
                counts['missing'] += 1
            else:
                value = row['dimensions'][dimension]['score']
                counts['not_applicable' if value is None else str(value)] += 1
        summary['dimensions'][dimension] = counts
    _write_json(Path(str(output) + '.summary.json'), summary)
    return summary
