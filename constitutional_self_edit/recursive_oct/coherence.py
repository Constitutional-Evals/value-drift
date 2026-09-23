"""Pairwise coherence comparison between two checkpoints, adapted from OCT paper Sec 3.4.

Paper departure: the paper judges coherence "given alignment with desired traits" for an
explicit, system-prompted persona. This project's constitution is trained into weights
rather than restated at inference (docs/method.md), so there is no persona for the judge to
check alignment against. The judge instead assesses general coherence -- staying on topic,
following through on its own approach, and specifically the repetition/looping degeneration
already documented in docs/STAGE2_REPORT.md. Every pair is judged in both response orders;
only judgments that agree on the winning checkpoint once the anonymized order is undone are
kept, following the paper's order-swap calibration (Sec 3.4). This module is judge-only: it
operates on already-saved held-out responses (e.g. eval_000.jsonl/eval_001.jsonl) and never
regenerates policy responses, so it never needs the student checkpoint reloaded.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

from .data import write_jsonl
from .editing import PROMPT_DIR
from .measurement import blind_response_pairs


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _write_json(path: Path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(str(path) + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def _freeze_json(path: Path, value) -> None:
    path = Path(path)
    if path.exists() and json.loads(path.read_text()) != value:
        raise ValueError(f'Existing coherence protocol/input differs: {path.name}; use a separately labeled analysis')
    if not path.exists():
        _write_json(path, value)


def parse_coherence_judgment(raw: str) -> dict:
    text = raw.strip()
    fence = re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```', text, re.S | re.I)
    if fence:
        text = fence[1].strip()
    try:
        obj = json.loads(text, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError('Judge output is not a complete JSON object') from exc
    if not isinstance(obj, dict) or set(obj) != {'more_coherent', 'rationale'}:
        raise ValueError('Judge output must contain exactly more_coherent and rationale')
    if obj['more_coherent'] not in ('A', 'B', 'tie'):
        raise ValueError('more_coherent must be A, B, or tie')
    if not isinstance(obj['rationale'], str) or not obj['rationale'].strip() or len(obj['rationale'].split()) > 25:
        raise ValueError('rationale must be a nonempty string of at most 25 words')
    return obj


def build_order_swap_jobs(baseline_id: str, comparison_id: str, baseline_responses: list[dict],
                          comparison_responses: list[dict], seed: int = 20260915) -> tuple[list[dict], list[dict]]:
    """Anonymized pairs (via measurement.blind_response_pairs) plus their exact swap.

    Returns (jobs, key). jobs contains two judge inputs per pair ('-fwd' and '-swap'),
    carrying only the prompt and two anonymous responses -- never checkpoint identity.
    key maps each pair back to which real checkpoint supplied slot A/B in the forward job.
    """
    pairs, blind_key = blind_response_pairs(baseline_responses, comparison_responses, seed=seed)
    key = [{'pair_id': k['pair_id'],
            'response_a_checkpoint': str(baseline_id) if k['response_a_checkpoint'] == 'baseline' else str(comparison_id),
            'response_b_checkpoint': str(baseline_id) if k['response_b_checkpoint'] == 'baseline' else str(comparison_id)}
           for k in blind_key]
    jobs = []
    for pair in pairs:
        jobs.append({'id': pair['pair_id'] + '-fwd', 'prompt': json.dumps(
            {'prompt': pair['prompt'], 'response_a': pair['response_a'], 'response_b': pair['response_b']},
            ensure_ascii=False)})
        jobs.append({'id': pair['pair_id'] + '-swap', 'prompt': json.dumps(
            {'prompt': pair['prompt'], 'response_a': pair['response_b'], 'response_b': pair['response_a']},
            ensure_ascii=False)})
    return jobs, key


def run_coherence_eval(baseline_id, comparison_id, judge_checkpoint, baseline_responses: list[dict],
                       comparison_responses: list[dict], output_path, config: dict) -> dict:
    """Judge-only coherence comparison of two checkpoints' saved neutral held-out responses.

    config requires fixed_judge_checkpoint to equal judge_checkpoint. baseline_responses and
    comparison_responses are rows with (id, prompt, response) -- e.g. read from a saved
    eval_XXX.jsonl. Resumable: reruns with an unchanged protocol reuse cached judge
    generations via generate_rows.
    """
    expected = config.get('fixed_judge_checkpoint')
    if not expected or str(judge_checkpoint) != str(expected):
        raise ValueError('judge_checkpoint must match the explicitly frozen fixed_judge_checkpoint')
    output = Path(output_path)
    seed = config.get('seed', 20260915)
    jobs, key = build_order_swap_jobs(baseline_id, comparison_id, baseline_responses, comparison_responses, seed=seed)
    # Freezing the actual jobs (not just counts/identifiers) catches both a reseeded rerun
    # and a rerun over changed response content, matching judging.judge_responses's guard.
    _freeze_json(Path(str(output) + '.inputs.json'),
                {'baseline_checkpoint': str(baseline_id), 'comparison_checkpoint': str(comparison_id),
                 'judge_checkpoint': str(judge_checkpoint), 'seed': seed, 'jobs': jobs, 'key': key})
    write_jsonl(Path(str(output) + '.key.jsonl'), key)

    judge_system = (PROMPT_DIR / 'judge_coherence.md').read_text().strip()
    generation_config = {'enable_thinking': False, 'temperature': 0,
                          'max_new_tokens': config.get('max_new_tokens', 512),
                          'max_input_tokens': config.get('max_input_tokens', 8192),
                          'batch_size': config.get('batch_size', 8), 'seed': config.get('judge_seed', 314159)}
    for k in ('backend', 'vllm_python', 'vllm_engine', 'api_key', 'timeout', 'max_retries', 'referer', 'title'):
        if k in config:
            generation_config[k] = config[k]
    from .generation import generate_rows
    raw = generate_rows(judge_checkpoint, jobs, Path(str(output) + '.judge_raw.jsonl'), generation_config,
                        system=judge_system) if jobs else []
    raw_by_id = {r['id']: r for r in raw}

    records = []
    for k in key:
        pair_id = k['pair_id']
        record = {'pair_id': pair_id, 'response_a_checkpoint': k['response_a_checkpoint'],
                  'response_b_checkpoint': k['response_b_checkpoint']}
        try:
            forward, swapped = raw_by_id.get(pair_id + '-fwd'), raw_by_id.get(pair_id + '-swap')
            if forward is None or swapped is None:
                raise ValueError('Missing judge generation')
            if forward.get('finish_reason') != 'stop' or swapped.get('finish_reason') != 'stop':
                raise ValueError('Truncated judge generation')
            forward_verdict = parse_coherence_judgment(forward.get('text', ''))['more_coherent']
            swapped_verdict = parse_coherence_judgment(swapped.get('text', ''))['more_coherent']
            record['forward_verdict'], record['swapped_verdict'] = forward_verdict, swapped_verdict
            if forward_verdict == 'tie' or swapped_verdict == 'tie':
                record['status'] = 'tie'
            else:
                # The swap places original response_b in slot A; a stable winner flips its letter.
                forward_winner = k['response_a_checkpoint'] if forward_verdict == 'A' else k['response_b_checkpoint']
                swapped_winner = k['response_b_checkpoint'] if swapped_verdict == 'A' else k['response_a_checkpoint']
                if forward_winner == swapped_winner:
                    record['status'] = 'order_invariant'
                    record['winner'] = forward_winner
                else:
                    record['status'] = 'order_dependent'
        except (ValueError, TypeError, AttributeError) as exc:
            record.update(status='invalid_judge', error=str(exc))
        records.append(record)
    write_jsonl(output, records)

    status_counts = Counter(r['status'] for r in records)
    winners = Counter(r.get('winner') for r in records if r['status'] == 'order_invariant')
    summary = {'baseline_checkpoint': str(baseline_id), 'comparison_checkpoint': str(comparison_id),
              'judge_checkpoint': str(judge_checkpoint), 'pairs': len(records),
              'order_invariant': status_counts['order_invariant'],
              'order_dependent_excluded': status_counts['order_dependent'], 'ties': status_counts['tie'],
              'invalid_judge': status_counts['invalid_judge'],
              'baseline_wins': winners[str(baseline_id)], 'comparison_wins': winners[str(comparison_id)],
              'path': str(output)}
    _write_json(Path(str(output) + '.summary.json'), summary)
    return summary
