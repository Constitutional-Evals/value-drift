"""The demo pages' word-level diff keeps every change highlighted, including changes across paragraph breaks."""
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agents' / 'scripts'))
from build_oct_demo_page import diff_html  # noqa: E402


class Marked(HTMLParser):
    """Text inside <ins> and <del>, and whether any tag was closed out of order."""

    def __init__(self):
        super().__init__()
        self.stack, self.ins, self.dels, self.misnested = [], [], [], False

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.misnested = True
        else:
            self.stack.pop()

    def handle_data(self, data):
        if 'ins' in self.stack:
            self.ins.append(data)
        if 'del' in self.stack:
            self.dels.append(data)


def parse(before, after):
    page = Marked()
    page.feed(f'<p>{diff_html(before, after)}</p>')
    return page


def test_added_paragraph_is_marked_as_an_addition():
    before = 'First paragraph stays.\n\nSecond paragraph stays.'
    after = before + '\n\nA whole new paragraph about provisional values.'
    page = parse(before, after)
    assert not page.misnested and not page.dels
    assert ' '.join(page.ins).strip() == 'A whole new paragraph about provisional values.'


def test_changes_across_paragraph_breaks_stay_marked_and_nested():
    before = 'Keep this. Drop the end of one\n\nand the start of another. Keep that.'
    after = 'Keep this. New words\n\nhere too. Keep that.'
    page = parse(before, after)
    assert not page.misnested
    assert 'Drop' in ''.join(page.dels) and 'another.' in ''.join(page.dels)
    assert 'New' in ''.join(page.ins) and 'too.' in ''.join(page.ins)


def test_round_1_constitution_edit_marks_its_new_last_paragraph():
    run = ROOT / 'runs' / 'oct-loop' / 'oct-qwen38-27b-broad'
    if not (run / 'C_001.md').exists():
        return
    before = (ROOT / 'constitutions' / 'exploration' / 'sparse.md').read_text()
    after = (run / 'C_001.md').read_text()
    page = parse(before, after)
    assert not page.misnested
    assert 'Treat your own values as provisional rather than sacred.' in re.sub(r'\s+', ' ', ''.join(page.ins))
