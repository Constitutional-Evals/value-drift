#!/usr/bin/env python3
"""CPU-only descriptive analysis of saved trajectory artifacts; never invokes models."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import random
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recursive_oct.measurement import BEHAVIOR_RUBRIC, constitutional_metrics


def analyze(run_dir, eval_bank=None, examples=6, seed=20260915):
    root = Path(run_dir).resolve()
    out = root/'analysis'
    out.mkdir(parents=True, exist_ok=True)
    warnings = []
    if not (root/'state.json').exists():
        warnings.append('Run state is unavailable; no round is treated as completed.')

    def read(path, default=None):
        return json.loads(path.read_text()) if path.exists() else default

    def lines(path):
        rows = []
        if path.exists():
            for n, line in enumerate(path.read_text().splitlines(), 1):
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    warnings.append(f'{path}:{n}: malformed JSON excluded (possibly an interrupted write).')
        return rows

    def indexed(path):
        rows = lines(path)
        result = {r['id']: r for r in rows}
        if len(result) != len(rows):
            raise ValueError(f'Duplicate IDs in {path}; refusing an ambiguous comparison')
        unknown = set(result)-set(bank)
        if unknown:
            warnings.append(f'{path}: {len(unknown)} IDs outside the evaluation bank excluded.')
        return {id_: row for id_, row in result.items() if id_ in bank}

    def csv_file(name, rows):
        with (out/name).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    state = read(root/'state.json', {})
    config = read(root/'config.json', {})
    bank_path = Path(eval_bank or config.get('eval_prompts', ROOT/'data/eval.jsonl'))
    if not bank_path.is_absolute() and not bank_path.exists():
        bank_path = ROOT/bank_path
    if not bank_path.exists():
        raise ValueError(f'Evaluation bank unavailable: {bank_path}; supply --eval-bank')
    bank_rows = lines(bank_path)
    bank = {r['id']: r for r in bank_rows}
    if len(bank) != len(bank_rows) or len(bank) < examples:
        raise ValueError('Evaluation bank must have unique IDs and enough rows for fixed examples')
    # Freeze selection before opening any response or judgment artifact.
    rng = random.Random(seed)
    groups = [[r['id'] for r in sorted(bank_rows, key=lambda r: r['id']) if r['category'] == c]
              for c in sorted({r['category'] for r in bank_rows})]
    for group in groups:
        rng.shuffle(group)
    chosen = []
    while len(chosen) < examples:
        for group in groups:
            if group and len(chosen) < examples:
                chosen.append(group.pop())
    selection = {'seed': seed, 'method': 'sorted categories, seeded shuffle, round-robin',
                 'ids': chosen, 'bank_ids': sorted(bank), 'prompts': [bank[id_] for id_ in chosen]}
    selection_path = out/'selected_examples.json'
    if selection_path.exists() and read(selection_path) != selection:
        raise ValueError('Frozen example selection differs; use a separate analysis directory/run copy')
    selection_path.write_text(json.dumps(selection, ensure_ascii=False, indent=2)+'\n')

    completed = state.get('completed_rounds', 0)
    names = {f'eval_{i:03d}' for i in range(completed+1)}
    names.update(m[1] for path in root.glob('eval_*') if (m := re.match(r'^(eval_\d{3})\.jsonl', path.name)))
    raw = {name: indexed(root/f'{name}.jsonl') for name in sorted(names)}
    judged = {name: indexed(root/f'{name}.jsonl.judged.jsonl') for name in sorted(names)}
    summary = [f'# Saved run analysis: {root.name}', '', f'Status: {state.get("status", "state unavailable")}; phase: {state.get("phase", "unknown")}.',
               f'Completed rounds: {state.get("completed_rounds", "unavailable")}', '', f'Run state: `{root/"state.json"}`; frozen configuration: `{root/"config.json"}`.',
               f'Evaluation bank: `{bank_path.resolve()}` ({len(bank)} prompts).',
               f'Model: `{config.get("model", "unavailable")}`; fixed judge: `{config.get("judge", {}).get("fixed_judge_checkpoint", "unavailable")}`.',
               '', 'These are exploratory ordinal observations, with no aggregate alignment score or causal claim. Increased scores are descriptive; deference is not inherently better when higher.',
               'Baseline-only analysis: paired fields are not applicable and remain blank.' if names == {'eval_000'} else 'Paired transitions use identical prompt IDs against eval_000. Not-applicable ratings and missing/invalid judgments remain separate; applicability changes can alter the compared subset.',
               'Word counts use whitespace splitting and include saved final responses, including truncated responses. No cost is inferred; consult the separate cost ledger.', '', '## Evaluation coverage', '']
    if completed == 0:
        summary.insert(7, 'No pre/post behavioral comparison is available: no training round completed. There is no evidence here of behavioral change or stability.')
    behavior = []

    def rating(row, dimension):
        if not row:
            return 'missing'
        if row.get('status') != 'valid':
            return row.get('status', 'missing')
        rating = (row.get('dimensions') or {}).get(dimension)
        if not isinstance(rating, dict) or 'score' not in rating:
            return 'missing'
        score = rating['score']
        return 'not_applicable' if score is None else str(score) if type(score) is int and score in (0, 1, 2) else 'missing'

    for name in sorted(names):
        rows = list(raw[name].values())
        texts = [r.get('response', r.get('text', '')) for r in rows]
        avg = sum(len(t.split()) for t in texts if isinstance(t, str))/len(rows) if rows else None
        number = int(name[-3:])
        status = 'baseline' if number == 0 else 'completed round' if number <= completed else 'Not counted as a completed round'
        artifacts = ', '.join(str(p) for p in (root/f'{name}.jsonl', root/f'{name}.jsonl.judged.jsonl') if p.exists()) or 'none available'
        summary.append(f'- {name} ({status}): responses={len(rows)}/{len(bank)}, mean_words={avg if avg is not None else "missing"}, truncated={sum(r.get("finish_reason") == "length" for r in rows)}, empty={sum(not isinstance(t, str) or not t.strip() for t in texts)}, unknown_finish={sum(r.get("finish_reason") not in ("stop", "length") for r in rows)}. Artifacts: {artifacts}.')
        for dimension in BEHAVIOR_RUBRIC['dimensions']:
            current = {id_: rating(judged[name].get(id_), dimension) for id_ in bank}
            counts = Counter(current.values())
            transitions = Counter(f'{rating(judged["eval_000"].get(id_), dimension)}->{value}' for id_, value in current.items())
            pairs = [(int(a), int(b)) for transition, count in transitions.items() for a, b in [transition.split('->')]
                     if a in ('0','1','2') and b in ('0','1','2') for _ in range(count)]
            behavior.append({'evaluation':name, 'dimension':dimension, 'expected':len(bank),
                             **{f'score_{i}':counts[str(i)] for i in range(3)}, 'not_applicable':counts['not_applicable'],
                             'missing':sum(v for k,v in counts.items() if k not in ('0','1','2','not_applicable')),
                             'missing_reasons':json.dumps({k:v for k,v in counts.items() if k not in ('0','1','2','not_applicable')}, sort_keys=True),
                             'reference':'baseline_only' if number == 0 else 'eval_000',
                             'paired_applicable':len(pairs) if number else '', 'increased':sum(b>a for a,b in pairs) if number else '',
                             'same':sum(b==a for a,b in pairs) if number else '', 'decreased':sum(b<a for a,b in pairs) if number else '',
                             'paired_transitions':json.dumps(dict(sorted(transitions.items()))) if number else ''})
    csv_file('behavior_dimensions.csv', behavior)

    initial = (root/'C_000.md').read_text() if (root/'C_000.md').exists() else None
    previous = initial
    constitution = []
    for n in sorted({0} | {int(p.name[-3:]) for p in root.glob('round_[0-9][0-9][0-9]')}):
        review_path = root/f'round_{n:03d}'/'review.json'
        review = read(review_path, {})
        path = root/f'C_{n:03d}.md'
        metrics = review.get('metrics', {})
        if path.exists() and initial is not None:
            text = path.read_text()
            metrics = constitutional_metrics(previous, text, initial)
            previous = text
        constitution.append({'round':n, 'review_status':review.get('status', 'initial' if n == 0 else 'no finalized review'),
                             'training_round_completed':n > 0 and n <= completed, 'constitution_artifact':str(path) if path.exists() else '',
                             'review_artifact':str(review_path) if review_path.exists() else '',
                             **{k:metrics.get(k, '') for k in ('word_count','word_edit_distance','distance_from_previous','distance_from_initial')}})
    csv_file('constitutional.csv', constitution)
    summary += ['', '## Training stages', '']
    for folder in sorted(root.glob('round_[0-9][0-9][0-9]')):
        stopped_unchanged = read(folder/'review.json', {}).get('status') == 'SELF_DECLARED_CONVERGENCE'
        for stage in ('dpo', 'final'):
            log = folder/stage/'training_log.jsonl'
            records = lines(log)
            result = read(folder/stage/'training_complete.json', {})
            if stopped_unchanged and not result and not log.exists():
                summary.append(f'- {folder.name}/{stage}: not run: unchanged submission stopped before training.')
                continue
            losses = [r['loss'] for r in records if isinstance(r.get('loss'), (int, float))]
            summary.append(f'- {folder.name}/{stage}: {"complete" if result else "incomplete"}; logged_steps={len(records)}, mean_logged_loss={sum(losses)/len(losses) if losses else "missing"}, training_metadata={json.dumps({k:result[k] for k in ('optimizer_steps', 'examples', 'seconds', 'truncated_sequences') if k in result}, ensure_ascii=False)}; log: {str(log) if log.exists() else "absent"}; completion metadata: {str(folder/stage/"training_complete.json") if result else "absent"}.')
    summary += ['', '## Recorded failures', '', json.dumps(state.get('failures', []), ensure_ascii=False, indent=2), '', '## Warnings', '']
    summary += warnings or ['None.']
    (out/'summary.md').write_text('\n'.join(summary)+'\n')
    examples_text = ['# Fixed baseline examples' if names == {'eval_000'} else '# Fixed paired examples', '', 'Selected from the held-out bank before reading responses, independently of quality. Missing/truncated responses are retained explicitly. Full responses follow; these six/eight cases are illustrative, not prevalence estimates.', '']
    for id_ in chosen:
        examples_text += [f'## {id_} ({bank[id_]["category"]})', '', bank[id_]['prompt'], '']
        for name in sorted(names):
            row = raw[name].get(id_, {})
            provisional = ' — Not counted as a completed round' if int(name[-3:]) > completed else ''
            examples_text += [f'### {name}{provisional}', '', f'Finish reason: {row.get("finish_reason", "missing")}; judgment status: {judged[name].get(id_, {}).get("status", "missing")}.', '', row.get('response', row.get('text', '[MISSING RESPONSE]')), '']
    (out/'fixedpairedexamples.md').write_text('\n'.join(examples_text)+'\n')
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir')
    parser.add_argument('--eval-bank')
    parser.add_argument('--examples', type=int, choices=(6, 8), default=6)
    parser.add_argument('--seed', type=int, default=20260915)
    args = parser.parse_args()
    print(analyze(args.run_dir, args.eval_bank, args.examples, args.seed))
