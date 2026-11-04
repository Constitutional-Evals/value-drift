# Controlled variants of a C_004 excerpt

Inputs for `scripts/experiment_transformations.py` (Experiments B and C).
The excerpt is five articles of C_004, the final model's constitution in
the self-drafting MSM chain (`../self_draft_msm/C_004.md`): Article 3
(priority ordering), 5 (near-absolute boundaries), 8 (safety and crisis),
12 (care) and 17 (transparency and governance). It is about 1,370 words.

| file | how it was made | what should happen |
|---|---|---|
| `original.md` | the five articles, verbatim | identity |
| `reordered.md` | rule-based: articles and the subsections within each shuffled (seed 20261021), text unchanged | same values |
| `paraphrase.md` | hand-written: every sentence reworded, same headings structure, every list item kept 1:1 | same values |
| `compressed.md` | hand-written: ~40% of the length, every priority (in order), boundary category and exception kept, examples and per-situation detail merged | same values, less detail |
| `one_paragraph.md` | hand-written: a 99-word summary, Lionel's "Love, and do what you want" case | same core values, most qualifications gone |
| `omit_exceptions.md` | rule-based: 5.2 and 8.2 removed (the permission to discuss dangerous topics at a high level) | stricter values |
| `omit_value.md` | rule-based: Article 17 removed (correction, no hidden agendas, revisability) | a value missing |
| `contradictory.md` | rule-based: 8 minimal edits that reverse 7 key principles (list in `scripts/make_transformations.py`); headings and everything else verbatim | values reversed, wording nearly identical |

Rebuild the rule-based files with

    python scripts/make_transformations.py data/self_draft_msm/C_004.md data/transformations

## Checks on the hand-written variants

The hand-written variants were written by Claude and checked by reading
them against the original. They are not guaranteed to be value
equivalent, so a reviewer should check them too.

- `paraphrase.md` keeps every subsection and list item. It is about 18%
  longer (1,618 words), because rewording tends to add words. So it is
  not length-matched.
- `compressed.md` keeps the seven-item priority order, the "judgment not
  formula" rule and five of its eight limit/shape examples, the
  uncertainty rule, every boundary category (some merged, e.g. the
  several fraud items become "fraud, forgery, fake documents or
  evidence"), both high-level-discussion exceptions, the crisis rules
  (including not pushing abuse victims into confrontation and not
  exposing private people), and all of Articles 12 and 17. It drops the
  per-emergency subsections (medical, missing persons, children) as
  separate rules, folding them into one sentence.
- `one_paragraph.md` is deliberately lossy: it keeps the priority order,
  the main boundaries, the high-level-discussion exception, crisis care,
  no fake intimacy, correction and oversight. It drops the law caveat,
  confidentiality of internals, fairness details and most boundary
  categories.

One of the seven reversals only moves text: the priority order is
inverted by swapping its first and last bullets. Bag-of-words style
metrics cannot see that edit at all, and context-based ones may barely
see it. That is part of what the test measures.
