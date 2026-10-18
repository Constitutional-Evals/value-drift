"""The long-writing diagnostic: its inputs, paired seeds, and how replies are scored."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agents' / 'scripts'))
import long_writing_diagnostic as D  # noqa: E402
import prepare_long_writing as P  # noqa: E402


def reply(finish, content, reasoning='Some thinking.'):
    return {'choices': [{'finish_reason': finish, 'message': {'content': content, 'reasoning': reasoning}}]}


def test_inputs_and_paired_seeds():
    items = D.items()
    assert [t for t, _ in items].count('writing') == 10 and [t for t, _ in items].count('summary') == 5
    assert all('No particular length is expected' in item['prompt'] for _, item in items)
    summaries = [item for task, item in items if task == 'summary']
    assert all(24000 < item['words'] < 27000 and '<text>' in item['prompt'] for item in summaries)
    first, again = D.jobs(2, 7), D.jobs(2, 7)
    assert len(first) == 30 and [j[4]['seed'] for j in first] == [j[4]['seed'] for j in again]
    assert len({j[4]['seed'] for j in first}) == 30 and first[0][4]['temperature'] == 1.0


def test_outcomes_and_metrics():
    assert D.outcome(reply('stop', '# Guide\n\nText.')) == 'finished'
    assert D.outcome(reply('stop', None)) == 'no_text' and D.outcome(reply('stop', '```\n\n```')) == 'no_text'
    assert D.outcome(reply('loop', None)) == 'loop' and D.outcome(reply('length', 'Partial')) == 'length'
    assert D.outcome(None) == 'error'
    records = [('writing', 'finished', 3000, 900), ('writing', 'loop', 0, 8000), ('summary', 'no_text', 0, 5000),
               ('summary', 'finished', 1200, 700)]
    m = D.metrics(records)
    assert m['writing']['finished'] == 0.5 and m['writing']['loop'] == 0.5 and m['writing']['median_text_words_finished'] == 3000
    assert m['summary']['no_text'] == 0.5 and m['summary']['median_reasoning_words'] == 2850
    table = D.table({'base': m, 'r1': m})
    assert '| writing | finished | 0.5 | 0.5 |' in table


def test_excerpt_drops_the_credit_line_and_cuts_at_a_paragraph():
    text = 'Produced by Someone and the Team\nat pgdp\n\nTITLE\n\n' + '\n\n'.join(' '.join(['word'] * 400) for _ in range(10))
    cut, words = P.excerpt(text, words=1000)
    assert not cut.startswith('Produced') and cut.startswith('TITLE') and words == 1201
