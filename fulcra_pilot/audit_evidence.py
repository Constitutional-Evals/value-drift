"""Audit each value separately in saved Schwartz replies, without new API calls.

Secondary analysis: retain the original whole-response rejection report alongside this one.
"""
import argparse
import json
from collections import Counter
from pathlib import Path
from pilot import VALUES, prepare, validate
from run_openrouter import parse_json, read_json, write_json


def check_value(request, rating, key):
    # Other dimensions are placeholders used solely to reuse the strict schema validator.
    # They never become observations or count toward any empirical summary.
    partial = {'protocol': request['protocol'], 'document_sha256': request['document_sha256'],
               'annotator': 'per-value-structural-audit', 'values': {
                   k: {'label': 'not_evidenced', 'evidence': [], 'rationale': 'Validation placeholder.'}
                   for k in VALUES}}
    partial['values'][key] = rating['values'][key]
    validate(request, partial)


def audit(folder):
    manifest = read_json(folder / 'manifest.json')
    counts, failures, observations = {}, [], []
    for item in manifest['inputs']:
        version = item['version']
        request = prepare(item['text'])
        counters = {k: Counter() for k in VALUES}
        for repeat in range(1, manifest['repeats'] + 1):
            raw = read_json(folder / f'{version}.schwartz.{repeat}.raw.json')
            choice = raw['choices'][0]
            if choice.get('finish_reason') != 'stop':
                raise ValueError('Incomplete response; do not audit partial JSON')
            rating = parse_json(choice['message']['content'])
            if set(rating.get('values', {})) != set(VALUES):
                raise ValueError('Unexpected value schema')
            for key in VALUES:
                try:
                    check_value(request, rating, key)
                except (ValueError, TypeError, KeyError) as exc:
                    failures.append({'version': version, 'repeat': repeat,
                                     'value': key, 'error': str(exc)})
                else:
                    counters[key][rating['values'][key]['label']] += 1
                    observations.append({'version': version, 'repeat': repeat, 'value': key,
                                         **rating['values'][key]})
        counts[version] = {k: dict(v) for k, v in counters.items()}
    write_json(folder / 'per_value_audit.json', {'counts': counts, 'failures': failures,
        'observations': observations, 'analysis': 'Secondary per-value evidence validation; '
        'no quote repair, no relabeling, no new calls. Structural validity is not semantic validity.'})
    lines = ['# Secondary per-value evidence audit', '',
        'This supplements the original strict whole-response validation in report.md.',
        'An invalid value annotation is excluded; other values in that reply are validated separately.',
        'No quotes were repaired, no labels changed, and no API calls repeated.',
        'This analysis was added after observing quote errors; it is exploratory.', '',
        '| Value | ' + ' | '.join(counts) + ' |', '|---|' + '---|' * len(counts)]
    for key in VALUES:
        cells = []
        for version in counts:
            c = counts[version][key]
            cells.append(', '.join(f'{label}: {n}' for label, n in sorted(c.items()))
                         + f' (valid n={sum(c.values())})')
        lines.append('| ' + key + ' | ' + ' | '.join(cells) + ' |')
    lines += ['', f'Excluded value annotations: {len(failures)}.', '',
        'These are one judge\'s descriptive labels. Repetition is not independent validation.',
        'Subject distinctions remain in evidence; mixed subjects must not be read as one agent\'s preference.',
        'Inspect per_value_audit.json for every retained annotation and every exclusion.']
    (folder / 'per_value_audit.md').write_text('\n'.join(lines) + '\n')
    print(f'Per-value audit: {len(observations)} retained; {len(failures)} excluded')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    audit(parser.parse_args().folder)
