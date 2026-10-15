#!/usr/bin/env python3
"""Inputs for the long-writing diagnostic (agents/scripts/long_writing_diagnostic.py), in data/eval_suite/.

- long_writing.jsonl: 10 requests for a long document on topics unrelated to values, phrased like the
  self-drafting writing turn (recursive_oct/self_draft.WRITE): "Organize it however you think best. No
  particular length is expected, but it should be complete."
- long_summary.jsonl: the first ~25,000 words (cut at a paragraph) of 5 non-fiction books from the PG-19 test
  set (emozilla/pg19-test, pinned; public-domain Project Gutenberg books), about the length of the five drafts
  a consolidation reads, each with a request for a summary.

    python3 agents/scripts/prepare_long_writing.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / 'data' / 'eval_suite'
PG19 = ('emozilla/pg19-test', 'c5e39bf32e33f9111323aa68d7d9000d22722035', 'data/test-00000-of-00001-29a571947c0b5ccc.parquet')
BOOKS = ('Travels in Morocco Volume 2', 'The Wonders Of Instinct', 'Notes on Railroad Accidents',
         'A Treatise on Painting', 'Musical Instruments')
EXCERPT_WORDS = 25000
TOPICS = (
    'a guide to baking sourdough bread at home, from creating a starter to troubleshooting common problems',
    'a history of the steam engine, from the earliest atmospheric engines to the steam turbine',
    'a technical manual for setting up, securing, and maintaining a home computer network',
    'a textbook chapter on plate tectonics: the evidence for it, its mechanisms, and its role in earthquakes, '
    'volcanoes, and mountain building',
    'a travel guide to the national parks of the American Southwest',
    'a guide to learning chess, from the rules to opening principles, middlegame strategy, and basic endgames',
    'an explanation of how a compiler works, from lexical analysis to code generation, with worked examples',
    'a handbook for growing vegetables in a small urban garden through the whole year',
    'an account of the life cycle of stars, from molecular clouds to white dwarfs, neutron stars, and black holes',
    'a guide to traditional woodworking joinery: the main joints, how to cut them by hand, and when to use each',
)
WRITE = ('Write {topic}. Organize it however you think best. No particular length is expected, but it should be '
         'complete. Reply with the document only.')
SUMMARIZE = ('Below is the beginning of a book. Read it carefully, then write a summary of it that covers its '
             'content in order. No particular length is expected, but it should be complete. Reply with the summary '
             'only.\n\n<text>\n{text}\n</text>')


def excerpt(text, words=EXCERPT_WORDS):
    """The text without the transcriber's credit line, cut after the paragraph that reaches `words` words."""
    lines = text.lstrip().split('\n')
    if lines and lines[0].strip().startswith(('Produced by', 'E-text prepared by')):
        while lines and lines[0].strip():
            lines.pop(0)
    out, count = [], 0
    for paragraph in '\n'.join(lines).strip().split('\n\n'):
        out.append(paragraph)
        count += len(paragraph.split())
        if count >= words:
            break
    return '\n\n'.join(out).strip(), count


def main():
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download
    repo, revision, filename = PG19
    rows = pq.read_table(hf_hub_download(repo, filename, repo_type='dataset', revision=revision)).to_pylist()
    with open(SUITE / 'long_writing.jsonl', 'w') as stream:
        for i, topic in enumerate(TOPICS, 1):
            stream.write(json.dumps({'id': f'write-{i:02d}', 'prompt': WRITE.format(topic=topic)}) + '\n')
    with open(SUITE / 'long_summary.jsonl', 'w') as stream:
        for i, title in enumerate(BOOKS, 1):
            book = next(r for r in rows if r['short_book_title'].startswith(title))
            text, words = excerpt(book['text'])
            stream.write(json.dumps({'id': f'summary-{i:02d}', 'title': book['short_book_title'], 'url': book['url'],
                                     'words': words, 'prompt': SUMMARIZE.format(text=text)}, ensure_ascii=False) + '\n')
    manifest = json.loads((SUITE / 'manifest.json').read_text())
    manifest['sources']['pg19_test'] = {'repo': repo, 'revision': revision, 'file': filename}
    manifest['counts'].update({'long_writing': len(TOPICS), 'long_summary': len(BOOKS)})
    (SUITE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'long_writing': len(TOPICS), 'long_summary': len(BOOKS)}))


if __name__ == '__main__':
    main()
