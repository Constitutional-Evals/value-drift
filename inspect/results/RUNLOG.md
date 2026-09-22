# Run log

Every experiment that has produced results, newest first. Each row links to its writeup;
the machine-readable version of this same list is [runs.yaml](runs.yaml), which
`scripts/check_docs.py` validates against what's actually on disk.

| id | date | question | models | runs | cost | writeup |
|---|---|---|---|---|---|---|
| `r3-eb-seeds` | 2026-09-16 | What do three different models do with a value-loaded constitution they may disagree with? | Sonnet 5, gpt-5, DeepSeek v3.1 | 48 | $1.48 | [r3-eb-seeds.md](r3-eb-seeds.md) |
| `r2-cheap` | 2026-09-10 | Does the model edit when nobody asks it to? | Sonnet 5 | 48 | $2.09 | [r2-cheap.md](r2-cheap.md) |

**Total: 96 runs, $3.57.**

---

## What each one found, in one line

- **`r2-cheap`**, editing is entirely instruction-driven (0/16 uninstructed vs 15/16
  when invited), and what the model does depends on whether it agrees with the document:
  zero deletions from the broad-consensus seed, 6 of 17 principles deleted from Marxism.

- **`r3-eb-seeds`**, the Marxism dismantling did *not* generalise to two other
  value-loaded seeds. All three models instead grafted a safety floor onto the doctrine
  and left it standing, with one exception where DeepSeek replaced a doctrine wholesale.

---

## Adding a run

See [docs/running-your-own.md](../docs/running-your-own.md). The short version: give it
an id, point `--log-dir` at `logs/<id>/<model-slug>/`, export it, write it up here, and
add it to `runs.yaml`, `scripts/check_docs.py` fails if a log directory has no entry.
