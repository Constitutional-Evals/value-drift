#!/usr/bin/env python3
"""CPU-only paired analysis of one saved OCT intervention; missing stages stay pending."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from recursive_oct.measurement import BEHAVIOR_RUBRIC
from analyze_edit_only import collect


def read(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default


def rows(path):
    path = Path(path)
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def indexed(path, bank):
    data = rows(path)
    result = {r['id']: r for r in data}
    if len(data) != len(result): raise ValueError(f'Duplicate IDs: {path}')
    if set(result)-set(bank): raise ValueError(f'IDs outside the fixed evaluation bank: {path}')
    for key, row in result.items():
        if 'prompt' in row and row['prompt'] != bank[key]['prompt']:
            raise ValueError(f'Prompt mismatch for {key}: {path}')
    return result


def lengths(values):
    return {'n': len(values), 'mean': statistics.mean(values) if values else None,
            'median': statistics.median(values) if values else None,
            'minimum': min(values) if values else None, 'maximum': max(values) if values else None}


def repetition(text):
    """Conservative descriptive flag; repeated short phrases alone do not qualify."""
    total = len(text.split())
    candidates = []
    for units in (text.splitlines(), re.split(r'(?<=[.!?])\s+', text)):
        normalized = [' '.join(unit.split()) for unit in units]
        counts = Counter(unit for unit in normalized if len(unit.split()) >= 5)
        for unit, count in counts.items():
            if count >= 3:
                excess = (count-1)*len(unit.split())
                candidates.append({'copies': count, 'unit_words': len(unit.split()),
                                   'excess_word_fraction': excess/max(total, 1)})
    worst = max(candidates, key=lambda x: x['excess_word_fraction'], default=None)
    return {'flagged': bool(worst and (worst['excess_word_fraction'] >= .2 or worst['copies'] >= 10)),
            'strongest_repeat': worst}


def response_summary(raw, expected):
    details = {}
    for key, row in raw.items():
        text = row.get('response', row.get('text', ''))
        if not isinstance(text, str): text = ''
        details[key] = {'words': len(text.split()), 'empty': not text.strip(),
                        'finish_reason': row.get('finish_reason'), **repetition(text)}
    return {'status': 'PENDING' if not raw else 'COMPLETE' if len(raw) == expected else 'PARTIAL',
            'available': len(raw), 'expected': expected, 'missing': expected-len(raw),
            'normal_stop': sum(d['finish_reason'] == 'stop' for d in details.values()),
            'caps': sum(d['finish_reason'] == 'length' for d in details.values()),
            'other_finish': sum(d['finish_reason'] not in ('stop', 'length') for d in details.values()),
            'empty': sum(d['empty'] for d in details.values()),
            'repetition_flags': sum(d['flagged'] for d in details.values()),
            'words_all': lengths([d['words'] for d in details.values()]), 'details': details}


def rating(row, dimension):
    if not row: return 'missing'
    if row.get('status') != 'valid': return row.get('status', 'missing')
    value = (row.get('dimensions') or {}).get(dimension, {}).get('score', 'missing')
    return 'not_applicable' if value is None else str(value) if type(value) is int and value in (0,1,2) else 'missing'


def paired_reviews(before_path, after_path):
    output = {'before': 'PENDING', 'after': 'PENDING', 'pairs': []}
    suites = []
    for name, path in [('before', before_path), ('after', after_path)]:
        if not path or not (Path(path)/'summary.json').exists():
            suites.append({}); continue
        summary = collect(path)
        output[name] = summary['suite_status']
        mapped = {(t['label'],t['seed']): t for t in summary['trajectories']}
        if len(mapped) != len(summary['trajectories']): raise ValueError('Duplicate review label/seed')
        suites.append(mapped)
    for key in sorted(set(suites[0]) | set(suites[1])):
        a, b = suites[0].get(key), suites[1].get(key)
        if a and b:
            initial_a, initial_b = [Path(path)/key[0]/'C_000.md' for path in (before_path, after_path)]
            if initial_a.exists() and initial_b.exists() and initial_a.read_bytes() != initial_b.read_bytes():
                raise ValueError(f'Paired reviews do not start with the same constitution: {key}')
        pair = {'label': key[0], 'initial_seed': key[1]}
        for name, item in [('before',a), ('after',b)]:
            pair[name] = None if item is None else {
                'status': item['status'], 'completed_reviews': item['completed_reviews'],
                'edited_reviews': item['edited_reviews'], 'content_changing_edits': item['content_changing_edits'],
                'first_review_status': item['reviews'][0]['status'] if item['reviews'] else None,
                'distance_from_initial': item['documents'][-1]['distance_from_initial'] if item['documents'] else None,
                'review_records': item['reviews']}
        output['pairs'].append(pair)
    return output


def analyze(baseline_run, run, output, *, before_review=None, after_review=None, plot=False):
    baseline_run, run, output = map(Path, (baseline_run, run, output))
    bank_path = baseline_run/'inputs/eval_prompts.jsonl'
    if not bank_path.exists(): bank_path = ROOT/'data/eval.jsonl'
    bank_rows = rows(bank_path)
    bank = {r['id']: r for r in bank_rows}
    if not bank or len(bank) != len(bank_rows): raise ValueError('Fixed evaluation bank missing or non-unique')
    raw = [indexed(baseline_run/'eval_000.jsonl', bank), indexed(run/'eval_001.jsonl', bank)]
    judged = [indexed(baseline_run/'eval_000.jsonl.judged.jsonl', bank), indexed(run/'eval_001.jsonl.judged.jsonl', bank)]
    judges = {row.get('judge_checkpoint') for group in judged for row in group.values()}
    rubrics = {row.get('rubric_version') for group in judged for row in group.values()}
    if len(judges) > 1 or len(rubrics) > 1: raise ValueError('Fixed judge or rubric differs between checkpoints')
    judge_configs = [read(folder/f'{prefix}.jsonl.judged.jsonl.config.json')
                     for folder,prefix in [(baseline_run,'eval_000'),(run,'eval_001')]]
    if all(judge_configs) and judge_configs[0] != judge_configs[1]:
        raise ValueError('Saved fixed-judge configuration differs between checkpoints')
    responses = {label: response_summary(group, len(bank)) for label, group in zip(('before','after'),raw)}
    common_stop = [key for key in bank if all(key in group and group[key].get('finish_reason') == 'stop'
        and group[key].get('response',group[key].get('text','')).strip() for group in raw)]
    matched = {'n': len(common_stop), 'before': lengths([responses['before']['details'][k]['words'] for k in common_stop]),
               'after': lengths([responses['after']['details'][k]['words'] for k in common_stop]),
               'ids': common_stop}
    dimensions = []
    for dimension in BEHAVIOR_RUBRIC['dimensions']:
        values = [{key: rating(group.get(key), dimension) for key in bank} for group in judged]
        pairs = [(int(values[0][k]),int(values[1][k])) for k in bank
                 if values[0][k] in ('0','1','2') and values[1][k] in ('0','1','2')]
        dimensions.append({'dimension': dimension, 'expected': len(bank),
            'before': dict(Counter(values[0].values())), 'after': dict(Counter(values[1].values())),
            'paired_applicable': len(pairs), 'increased': sum(b>a for a,b in pairs),
            'unchanged': sum(b==a for a,b in pairs), 'decreased': sum(b<a for a,b in pairs),
            'delta_counts': dict(Counter(str(b-a) for a,b in pairs)),
            'all_rating_transitions': dict(Counter(f'{values[0][k]}->{values[1][k]}' for k in bank))})
    judgment_summary = {}
    for label, group in zip(('before','after'),judged):
        valid = [r for r in group.values() if r.get('status') == 'valid']
        judgment_summary[label] = {'available': len(group), 'expected': len(bank),
            'status_counts': dict(Counter(r.get('status','missing') for r in group.values())),
            'missing': len(bank)-len(group), 'valid': len(valid),
            'refusal_present': sum(r.get('refusal_present') is True for r in valid)}
    state = read(run/'state.json', {})
    training = {stage: read(run/folder/'training_complete.json',
                           state.get('stage_records', {}).get(stage, {}).get('training'))
                for stage,folder in [('dpo','dpo'),('sft','final')]}
    receipt_sources = {stage: str(run/folder/'training_complete.json')
                      if (run/folder/'training_complete.json').exists() else
                      f'{run}/state.json:stage_records.{stage}.training' if training[stage] else None
                      for stage,folder in [('dpo','dpo'),('sft','final')]}
    data = {'kind': 'paired_training_intervention_analysis', 'baseline_run': str(baseline_run),
        'intervention_run': str(run), 'state': state, 'expected_prompts': len(bank),
        'responses': responses, 'matched_completed_response_lengths': matched,
        'judge': next(iter(judges), None), 'judge_configs_match': True if all(judge_configs) else None,
        'judgments': judgment_summary, 'dimensions': dimensions,
        'paired_reviews': paired_reviews(before_review, after_review),
        'seed_mismatch_ids': [k for k in set(raw[0]) & set(raw[1])
                              if raw[0][k].get('generation_seed') != raw[1][k].get('generation_seed')],
        'training': training, 'training_receipt_sources': receipt_sources}
    output.mkdir(parents=True, exist_ok=True)
    (output/'comparison.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
    markdown(data, output)
    if plot: plot_responses(data, output)
    return data


def value(number):
    return 'pending' if number is None else f'{number:.1f}' if isinstance(number,float) else str(number)


def markdown(data, output):
    lines = ['# Paired training intervention: saved observations', '',
        f"The intervention is currently **{data['state'].get('status','pending')}**, at stage **{data['state'].get('phase','pending')}**. "
        f"The held-out bank contains {data['expected_prompts']} fixed prompts. This analysis reads saved outputs and does not generate new responses.", '']
    if data['responses']['after']['status'] != 'COMPLETE':
        lines += ['**The final response comparison is pending or incomplete. Missing outputs are not evidence of unchanged behavior.**', '']
    lines += ['| Checkpoint | Responses / expected | Normal stop | Capped | Empty | Repetition flags | Median words | Mean words |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for name in ('before','after'):
        row = data['responses'][name]
        counts = [str(row[key]) if row['available'] else 'pending' for key in ('normal_stop','caps','empty','repetition_flags')]
        lines.append(f"| {name} | {row['available']} / {row['expected']} | {' | '.join(counts)} | {value(row['words_all']['median'])} | {value(row['words_all']['mean'])} |")
    matched = data['matched_completed_response_lengths']
    lines += ['', f"Among the same {matched['n']} prompts with nonempty, normally completed responses at both checkpoints, "
        f"median length was {value(matched['before']['median'])} → {value(matched['after']['median'])} words and mean length "
        f"{value(matched['before']['mean'])} → {value(matched['after']['mean'])} words.", '',
        'Repetition flags are a conservative text heuristic: an identical line or sentence of at least five words appears at least three times, '
        'and its extra copies occupy at least 20% of the response, or it appears at least ten times. Flags require inspection; formatting and legitimate repetition can also trigger them. '
        'Length summaries above include capped outputs; the matched subset controls only for completion, not response quality.', '',
        '## Fixed-judge observations', '',
        'Each dimension retains its own denominator. A higher deference rating is descriptive, not inherently preferable. '
        'No aggregate alignment score is calculated. Score distributions below list counts at 0 / 1 / 2, followed by not-applicable and missing or invalid counts.', '',
        '| Dimension | Before: 0 / 1 / 2; NA; missing/invalid | After: 0 / 1 / 2; NA; missing/invalid | Comparable pairs | Increased / same / decreased |',
        '| --- | --- | --- | ---: | --- |']
    for row in data['dimensions']:
        cells=[]
        for name in ('before','after'):
            counts=row[name]
            missing=sum(v for k,v in counts.items() if k not in ('0','1','2','not_applicable'))
            cells.append(f"{counts.get('0',0)} / {counts.get('1',0)} / {counts.get('2',0)}; {counts.get('not_applicable',0)}; {missing}")
        lines.append(f"| {row['dimension']} | {cells[0]} | {cells[1]} | {row['paired_applicable']} | {row['increased']} / {row['unchanged']} / {row['decreased']} |")
    for name in ('before','after'):
        row=data['judgments'][name]
        lines += ['', f"{name.capitalize()}: {row['valid']} valid judgments out of {row['expected']} expected; "
            f"{row['refusal_present']} refusals among those {row['valid']} valid judgments. Missing: {row['missing']}; "
            f"recorded judgment statuses: {json.dumps(row['status_counts'])}."]
    reviews=data['paired_reviews']
    lines += ['', '## Paired constitution reviews', '',
        f"Before suite: **{reviews['before']}**. After suite: **{reviews['after']}**. "
        'The suites are independent edit-only trajectories starting from the same intervention constitution. Training does not reopen a stopped trajectory.', '',
        '| Initial seed | Before: status; edited reviews; final distance from start | After: status; edited reviews; final distance from start |',
        '| ---: | --- | --- |']
    for pair in reviews['pairs']:
        cells=[]
        for name in ('before','after'):
            row=pair[name]
            distance = 'pending' if row is None or row['distance_from_initial'] is None else f"{row['distance_from_initial']:.3f}"
            cells.append('pending' if row is None else f"{row['status']}; {row['edited_reviews']}; {distance}")
        lines.append(f"| {pair['initial_seed']} | {cells[0]} | {cells[1]} |")
    lines += ['', 'Reviews are paired by their initial seed and starting text. Later request seeds can diverge when one review makes more tool calls. '
        'Lexical distances include reordering and do not establish substantive value change. Reading the saved diffs and explanations remains necessary.', '',
        '## Recorded training lineage', '']
    for stage,receipt in data['training'].items():
        if receipt:
            lines += [f"- {stage.upper()}: `{receipt.get('input_checkpoint','unspecified')}` → "
                f"`{receipt.get('output_checkpoint','unspecified')}`. Receipt: `{data['training_receipt_sources'][stage]}`."]
        else: lines += [f'- {stage.upper()}: completion receipt pending.']
    lines += ['', 'Checkpoint locations are reported exactly as recorded; a saved receipt does not establish that its weights are present on this machine.', '',
        '## Interpretation limits', '',
        'This is a single exploratory training intervention with a fixed teacher and same-family judge. Differences can reflect training, sampling, style, completion rates, '
        'or changes in the subset with applicable judgments. The analysis does not establish that edit-only screens predict trained trajectories.', '',
        f"Among available paired evaluation IDs, recorded sampling-seed mismatches: {len(data['seed_mismatch_ids'])}. "
        'The JSON retains individual coverage, repetition details, rating transitions, stage receipts, and review summaries for inspection.', '']
    (output/'comparison.md').write_text('\n'.join(lines))


def plot_responses(data, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes=plt.subplots(1,2,figsize=(9,3.7))
    for index,name in enumerate(('before','after')):
        row=data['responses'][name]
        values=[item['words'] for item in row['details'].values()]
        if values: axes[0].boxplot([values],positions=[index],widths=.4,showfliers=True)
        else: axes[0].text(index,.5,'Pending',ha='center',transform=axes[0].get_xaxis_transform())
        bottom=0
        for key,color in [('normal_stop','#32828A'),('caps','#C47F37'),('other_finish','#AA4F59'),('missing','#DDE1E5')]:
            axes[1].bar(index,row[key],bottom=bottom,color=color,label=key.replace('_',' ') if index==0 else None)
            bottom+=row[key]
    axes[0].set_ylabel('Response words, including capped outputs')
    axes[1].set_ylabel('Fixed evaluation prompts')
    for ax in axes: ax.set_xticks([0,1],['Before','After']); ax.spines[['top','right']].set_visible(False)
    axes[1].legend(fontsize=8,frameon=False)
    fig.suptitle('Saved behavioral responses before and after one OCT intervention',fontsize=11)
    fig.tight_layout()
    for suffix in ('png','svg'): fig.savefig(output/f'response_comparison.{suffix}',dpi=180,bbox_inches='tight')
    plt.close(fig)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-run',required=True)
    parser.add_argument('--run',required=True)
    parser.add_argument('--before-review')
    parser.add_argument('--after-review')
    parser.add_argument('--output',required=True)
    parser.add_argument('--plot',action='store_true')
    args=parser.parse_args()
    result=analyze(args.baseline_run,args.run,args.output,before_review=args.before_review,
                   after_review=args.after_review,plot=args.plot)
    print(json.dumps({'final_responses':result['responses']['after']['status'],
                      'matched_completed_responses':result['matched_completed_response_lengths']['n'],
                      'paired_reviews_after':result['paired_reviews']['after']}))
