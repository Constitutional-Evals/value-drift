#!/usr/bin/env python3
"""Summarize saved editing-only API experiments without additional model calls."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from recursive_oct.api_screen import save

ROOT = Path('runs/api-screen-20260924')
MAIN_BATCHES = {'batch01-factorial', 'batch03-model-comparison', 'batch07-size-comparison'}


def main():
    rows, scheduled, chains, models = [], [], [], {}
    for plan_path in sorted(ROOT.glob('batch*/plan.json')):
        plan = json.loads(plan_path.read_text())
        models.update(plan['models'])
        for trial in plan['trials']:
            directory = plan_path.parent/trial['label']
            scheduled.append({'batch': plan['label'], 'trial': trial})
            results = []
            for path in sorted(directory.glob('review_*/result.json')):
                result = json.loads(path.read_text())
                call_cost, reasoning, output_tokens, seconds = 0., 0, 0, 0.
                served = set()
                errors = []
                for response_path in sorted(path.parent.glob('*/response.json')):
                    data = json.loads(response_path.read_text())
                    usage = data.get('usage', {})
                    call_cost += usage.get('cost') or 0
                    reasoning += usage.get('completion_tokens_details', {}).get('reasoning_tokens') or 0
                    output_tokens += usage.get('completion_tokens') or 0
                    served.add(data.get('provider', 'unknown'))
                    for choice in data.get('choices', []):
                        if choice.get('error'):
                            errors.append(choice['error'])
                row = {**result, 'batch': plan['label'], 'label': trial['label'],
                       'model_id': plan['models'][trial['model']]['id'],
                       'review_index': int(path.parent.name.split('_')[-1]),
                       'is_continuation': bool(trial.get('parent_review')),
                       'result_path': str(path), 'actual_usd': call_cost,
                       'reported_reasoning_tokens': reasoning, 'completion_tokens': output_tokens,
                       'providers': sorted(served), 'provider_errors': errors}
                rows.append(row)
                results.append(row)
            if trial.get('parent_review'):
                parent_path = Path(trial['parent_review'])/'result.json'
                parent = json.loads(parent_path.read_text())
                full = [parent] + results
                last_status = full[-1]['status']
                terminal = (last_status if last_status != 'EDITED' else
                            'REVIEW_LIMIT' if len(results) == trial['max_reviews'] else 'IN_PROGRESS')
                chains.append({'model': trial['model'], 'replicate': trial['replicate'],
                    'parent_review': trial['parent_review'], 'directory': str(directory),
                    'terminal_status': terminal, 'completed_reviews': len(full),
                    'edited_reviews': sum(x['status'] == 'EDITED' for x in full),
                    'words': [len(Path(trial['trajectory_origin']).read_text().split())] + [x['word_count'] for x in full],
                    'distance_from_initial': [0.] + [x['distance_from_initial'] for x in full],
                    'distance_from_previous': [0.] + [x['distance_from_previous'] for x in full]})
    first = [x for x in rows if not x['is_continuation']]
    primary = [x for x in first if x['batch'] in MAIN_BATCHES and x['config']['reflection'] == 'values']
    groups = defaultdict(Counter)
    for row in primary:
        groups[(row['config']['model'], row['config']['context'])][row['status']] += 1
    ledger = json.loads((ROOT/'ledger.json').read_text())
    summary = {
        'scheduled_first_reviews': sum(not x['trial'].get('parent_review') for x in scheduled),
        'completed_first_reviews': len(first), 'first_review_statuses': dict(Counter(x['status'] for x in first)),
        'all_completed_reviews': len(rows), 'all_review_statuses': dict(Counter(x['status'] for x in rows)),
        'primary_first_reviews': len(primary), 'models': models,
        'primary_model_context': [{'model': k[0], 'context': k[1], **v} for k,v in sorted(groups.items())],
        'continued_chains': chains,
        'actual_usd': sum(x.get('actual_usd', 0.) for x in ledger['calls'].values()),
        'unsettled_reserved_usd': sum(x['reserved_usd'] for x in ledger['calls'].values() if 'actual_usd' not in x),
        'request_count': len(ledger['calls']),
        'provider_error_count': sum(bool(x['provider_errors']) for x in rows),
    }
    save(ROOT/'analysis/reviews.json', rows)
    save(ROOT/'analysis/summary.json', summary)
    codes = []
    keys = {}
    for path in sorted((ROOT/'analysis').glob('semantic_codes*.json')):
        codes.extend(json.loads(path.read_text()))
    for path in sorted((ROOT/'analysis').glob('blind_edits*key.json')):
        keys.update({x['id']: x['result_path'] for x in json.loads(path.read_text())})
    if codes:
        joined = [{**x, 'result_path': keys[x['id']]} for x in codes]
        save(ROOT/'analysis/semantic_coding_joined.json', joined)
        save(ROOT/'analysis/semantic_summary.json', {
            'coded_edited_reviews': len(codes),
            'total_edited_reviews': sum(x['status'] == 'EDITED' for x in rows),
            'substantive': sum(x['substantive'] is True for x in codes),
            'not_substantive': sum(x['substantive'] is False for x in codes),
            'ambiguous': sum(x['substantive'] is None for x in codes),
            'quality_concern_flags': sum(bool(x.get('quality_concern')) for x in codes),
            'overlapping_categories': dict(Counter(c for x in codes for c in x['categories'])),
            'limitation': 'One blinded research-agent coder; broad action-relevant definition, not validated human judgment or a moral quality score.'})
    def link(path):
        return '../../' + str(path)
    text = ['# Constitutions from the September 24 API experiments', '',
            'These are editing-only experiments. No model weights were trained. Each review starts in a fresh conversation.', '',
            'The starting documents were the [227-word short constitution](../../constitutions/exploration/sparse.md) and, in the starting-document comparison, the [1,059-word original essay](../../constitutions/C_000.md). Both were drafted by the research agents before this round. Subsequent edits below were submitted by the named API models.', '',
            'Each row links the starting text, final working file, readable diff, public assessment when present, and structured outcome. An unchanged submission produces an identical final document. A **failed** review did not submit a valid decision: its working file is retained for diagnosis, not endorsed as a constitution. Raw private API reasoning is not reproduced in this index.', '',
            '## Longer editing sequences', '',
            '| Model / repetition | Words from original through every review | Edited reviews | Stop |',
            '|---|---|---:|---|']
    for chain in chains:
        text.append(f"| {chain['model']} / {chain['replicate']} | {' → '.join(map(str,chain['words']))} | {chain['edited_reviews']} | {chain['terminal_status']} |")
    for batch in sorted({x['batch'] for x in rows}):
        text.extend(['', '## '+batch, '', '| Model / context / review style / repetition | Review | Outcome | Files |', '|---|---:|---|---|'])
        for row in sorted([x for x in rows if x['batch']==batch], key=lambda x:(x['label'],x['review_index'])):
            c=row['config'];d=Path(row['result_path']).parent
            files=[f'[before]({link(d/"initial.md")})',f'[after]({link(d/"submitted.md")})',f'[diff]({link(d/"diff.patch")})',f'[outcome]({link(d/"result.json")})']
            if (d/'appraisal.md').exists():files.append(f'[assessment]({link(d/"appraisal.md")})')
            text.append(f"| {row['model_id']} / {c['context']} / {c['reflection']}{' (thinking off)' if not c.get('thinking',True) else ''} / {c['replicate']} | {row['review_index']} | {row['status']} | {' · '.join(files)} |")
    # Index lives two levels below the project root (reports/04_api_screen/), so links use ../../.
    Path('reports/04_api_screen/API_SCREEN_CONSTITUTIONS.md').write_text('\n'.join(text)+'\n')
    print(json.dumps({k:summary[k] for k in ['completed_first_reviews','scheduled_first_reviews','all_completed_reviews','first_review_statuses','actual_usd','unsettled_reserved_usd']},indent=2))


if __name__=='__main__':
    main()
