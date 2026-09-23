"""Revealed-preference trait evaluation, adapted from OCT paper Sec 3.1.

Paper departure: the paper elicits a choice between two personas the model was actually
fine-tuned on, using ~150 traits and 25,000 samples. This project trains one continuous,
recursively-edited constitution rather than discrete personas, so there is no fixed
trait/persona set to fine-tune toward. We reuse the paper's elicitation-and-judging
mechanics unchanged (silently adopt one of two named traits, judge which trait the
resulting response embodies, aggregate into Elo) as a content-free probe of which general
interaction traits a checkpoint gravitates toward -- run identically at every checkpoint so
Elo trajectories across recursive rounds are directly comparable. The trait bank
(data/traits.json) is a curated ~24-trait subset for pilot budget/scale, not the paper's
full list; see its note field. Only generate_rows (imported lazily inside functions) needs
a GPU; parsing, sampling, and Elo computation run on the CPU.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import random
import re
from string import Template

from .data import write_jsonl
from .editing import PROMPT_DIR

ROOT = Path(__file__).resolve().parents[1]
TRAITS_PATH = ROOT / 'data' / 'traits.json'


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
        raise ValueError(f'Existing trial protocol/input differs: {path.name}; use a separately labeled analysis')
    if not path.exists():
        _write_json(path, value)


def load_traits(path: str | Path | None = None) -> list[str]:
    data = json.loads(Path(path or TRAITS_PATH).read_text())
    traits = data['traits']
    if not isinstance(traits, list) or len(set(traits)) != len(traits) or len(traits) < 2:
        raise ValueError('Trait bank must list at least two unique traits')
    return traits


def render_trait_choice_prompt(trait_a: str, trait_b: str, constitution: str | None = None) -> str:
    """Optionally prepend constitution conditioning, matching generation.constitution_system's wording.

    constitution is inference-time conditioning (a system-prompt prefix), never trained
    into weights here -- this tests a different mechanism than the real full-parameter
    training pipeline and must not be presented as equivalent to it.
    """
    template = Template((PROMPT_DIR / 'revealed_preference_system.md').read_text())
    rendered = template.substitute(trait_a=trait_a, trait_b=trait_b)
    if constitution:
        from .generation import constitution_system
        rendered = constitution_system(constitution) + '\n\n' + rendered
    return rendered


def sample_trait_trials(traits: list[str], prompts: list[dict], count: int, seed: int = 20260915) -> list[dict]:
    """Deterministic trial sequence: same seed/traits/prompts give the same sequence at every checkpoint."""
    if not prompts:
        raise ValueError('At least one prompt is required to elicit trait choices')
    if count < 1:
        raise ValueError('count must be positive')
    rng = random.Random(seed)
    trials = []
    for i in range(count):
        a, b = rng.sample(traits, 2)
        if rng.getrandbits(1):
            a, b = b, a
        prompt = prompts[i % len(prompts)]
        trials.append({'trial_id': f'trial-{i:05d}', 'prompt_id': prompt['id'], 'prompt': prompt['prompt'],
                        'trait_a': a, 'trait_b': b})
    return trials


def parse_trait_choice(raw: str) -> dict:
    text = raw.strip()
    fence = re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```', text, re.S | re.I)
    if fence:
        text = fence[1].strip()
    try:
        obj = json.loads(text, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError('Judge output is not a complete JSON object') from exc
    if not isinstance(obj, dict) or set(obj) != {'chosen_trait', 'rationale'}:
        raise ValueError('Judge output must contain exactly chosen_trait and rationale')
    if obj['chosen_trait'] not in ('trait_a', 'trait_b', 'unclear'):
        raise ValueError('chosen_trait must be trait_a, trait_b, or unclear')
    if not isinstance(obj['rationale'], str) or not obj['rationale'].strip() or len(obj['rationale'].split()) > 25:
        raise ValueError('rationale must be a nonempty string of at most 25 words')
    return obj


def compute_elo(traits: list[str], outcomes: list[tuple[str, str, str]], k: float = 32.0,
                initial: float = 1000.0) -> dict[str, float]:
    """Sequential Elo update over decided trials only ('unclear'/invalid trials excluded).

    outcomes: (trait_a, trait_b, winner) with winner in {'a','b'}, in trial order. Order
    matters for the exact resulting ratings; use the same trial sequence at every
    checkpoint (see sample_trait_trials) so this is a fair comparison across rounds.
    """
    ratings = {trait: float(initial) for trait in traits}
    for trait_a, trait_b, winner in outcomes:
        if trait_a not in ratings or trait_b not in ratings:
            raise ValueError('Outcome references a trait outside the fixed trait list')
        if winner not in ('a', 'b'):
            raise ValueError("winner must be 'a' or 'b'")
        rating_a, rating_b = ratings[trait_a], ratings[trait_b]
        expected_a = 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))
        score_a = 1.0 if winner == 'a' else 0.0
        ratings[trait_a] = rating_a + k * (score_a - expected_a)
        ratings[trait_b] = rating_b + k * ((1.0 - score_a) - (1.0 - expected_a))
    return ratings


def run_revealed_preference_eval(checkpoint, judge_checkpoint, prompts: list[dict], output_path, config: dict,
                                 constitution: str | None = None) -> dict:
    """Elicit a silent trait choice per trial, judge it, and score fixed-trait Elo.

    config requires fixed_judge_checkpoint to equal judge_checkpoint, matching the fixed-
    judge guard used by judging.judge_responses. Resumable: reruns with the same output
    path and an unchanged trial protocol reuse cached generations via generate_rows.

    constitution, if given, conditions elicitation via an inference-time system-prompt
    prefix (generation.constitution_system) -- it is never trained into weights here. This
    tests whether prompting on a constitution shifts revealed preferences, a different
    mechanism than the real full-parameter training pipeline; do not conflate the two. It is
    frozen into the trial protocol so a rerun against a different constitution text cannot
    silently reuse a mismatched cache.
    """
    expected = config.get('fixed_judge_checkpoint')
    if not expected or str(judge_checkpoint) != str(expected):
        raise ValueError('judge_checkpoint must match the explicitly frozen fixed_judge_checkpoint')
    traits = load_traits(config.get('traits_path'))
    output = Path(output_path)
    trials = sample_trait_trials(traits, prompts, config.get('trials', 200), config.get('seed', 20260915))
    _freeze_json(Path(str(output) + '.trials.json'), {'traits': traits, 'trials': trials, 'constitution': constitution})

    elicit_rows = [{'id': t['trial_id'], 'messages': [
        {'role': 'system', 'content': render_trait_choice_prompt(t['trait_a'], t['trait_b'], constitution=constitution)},
        {'role': 'user', 'content': t['prompt']}]} for t in trials]
    generation_config = {k: config[k] for k in
                          ('enable_thinking', 'max_new_tokens', 'temperature', 'top_p', 'top_k',
                           'max_input_tokens', 'batch_size', 'seed', 'backend', 'vllm_python', 'vllm_engine', 'api_key', 'timeout', 'max_retries', 'referer', 'title')
                          if k in config}
    generation_config.setdefault('max_new_tokens', 768)
    from .generation import generate_rows
    responses = generate_rows(checkpoint, elicit_rows, Path(str(output) + '.responses.jsonl'), generation_config)
    responses_by_id = {r['id']: r for r in responses}

    judge_system = (PROMPT_DIR / 'judge_trait_choice.md').read_text().strip()
    jobs = []
    for t in trials:
        response = responses_by_id[t['trial_id']]
        text = response.get('text', '')
        if isinstance(text, str) and text.strip() and response.get('finish_reason') != 'length':
            content = json.dumps({'trait_a': t['trait_a'], 'trait_b': t['trait_b'], 'response': text},
                                  ensure_ascii=False)
            jobs.append({'id': t['trial_id'], 'prompt': content})
    judge_generation_config = {'enable_thinking': False, 'temperature': 0,
                                'max_new_tokens': config.get('judge_max_new_tokens', 512),
                                'max_input_tokens': config.get('judge_max_input_tokens', 4096),
                                'batch_size': config.get('judge_batch_size', config.get('batch_size', 8)),
                                'seed': config.get('judge_seed', 314159)}
    for k in ('backend', 'vllm_python', 'vllm_engine', 'api_key', 'timeout', 'max_retries', 'referer', 'title'):
        if k in config:
            judge_generation_config[k] = config[k]
    if jobs:
        raw_judgments = generate_rows(judge_checkpoint, jobs, Path(str(output) + '.judge_raw.jsonl'),
                                       judge_generation_config, system=judge_system)
    else:
        raw_judgments = []
        Path(str(output) + '.judge_raw.jsonl').touch(exist_ok=True)
    raw_by_id = {r['id']: r for r in raw_judgments}

    outcomes, records = [], []
    for t in trials:
        record = {'trial_id': t['trial_id'], 'prompt_id': t['prompt_id'], 'trait_a': t['trait_a'], 'trait_b': t['trait_b']}
        response = responses_by_id[t['trial_id']]
        text = response.get('text', '')
        if not isinstance(text, str) or not text.strip():
            record['status'] = 'empty_response'
        elif response.get('finish_reason') == 'length':
            record['status'] = 'truncated_response'
        else:
            raw = raw_by_id.get(t['trial_id'])
            try:
                if raw is None:
                    raise ValueError('Missing judge generation')
                if raw.get('finish_reason') != 'stop':
                    raise ValueError('Truncated judge generation')
                parsed = parse_trait_choice(raw.get('text', ''))
                record.update(parsed)
                record['status'] = 'valid'
                if parsed['chosen_trait'] in ('trait_a', 'trait_b'):
                    outcomes.append((t['trait_a'], t['trait_b'], 'a' if parsed['chosen_trait'] == 'trait_a' else 'b'))
            except (ValueError, TypeError, AttributeError) as exc:
                record.update(status='invalid_judge', error=str(exc))
        records.append(record)
    write_jsonl(output, records)

    elo = compute_elo(traits, outcomes)
    status_counts = Counter(r['status'] for r in records)
    summary = {'checkpoint': str(checkpoint), 'judge_checkpoint': str(judge_checkpoint), 'trials': len(trials),
               'constitution_conditioned': constitution is not None,
               'valid': status_counts['valid'], 'decided': len(outcomes),
               'unclear': sum(r.get('chosen_trait') == 'unclear' for r in records),
               'empty_response': status_counts['empty_response'], 'truncated_response': status_counts['truncated_response'],
               'invalid_judge': status_counts['invalid_judge'],
               'elo': dict(sorted(elo.items(), key=lambda kv: -kv[1])), 'path': str(output)}
    _write_json(Path(str(output) + '.summary.json'), summary)
    return summary
