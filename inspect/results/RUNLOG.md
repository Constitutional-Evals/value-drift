# Run log

Every experiment that has produced results, newest first. Each row links to its writeup;
the machine-readable version of this same list is [runs.yaml](runs.yaml), which
`scripts/check_docs.py` validates against what's actually on disk.

| id | date | question | models | runs | cost | writeup |
|---|---|---|---|---|---|---|
| `chains-main` | 2026-09-22 | What happens to a constitution across repeated rounds of a model authoring its own successor's values? | Sonnet 5, gpt-5, DeepSeek v3.1 | 165 | ~$8.30 | [chains-main.md](chains-main.md) |

---

## Earlier work

[`results/archive/`](archive/) holds two single-shot experiments from September 2026, in
which a model was given one constitution and one opportunity to edit it. They used a
different design, different starting documents, and asked a different question, so they
are not a baseline for the recursive runs and nothing in the current results is compared
against them. They are kept because they are the only record of those runs.

---

## Adding a run

See [docs/running-your-own.md](../docs/running-your-own.md). Give it an id, keep its
output under `chains/<id>/<model-slug>/` (or `logs/<id>/<model-slug>/` for a single-shot
eval), write it up here, and add it to `runs.yaml`. `scripts/check_docs.py` fails if a
run directory has no entry.
