# scripts/

None of these contain experiment logic. The experiment lives in
`constitutional_drift/`; these just call `inspect eval` with the right flags, or read
logs back out afterwards.

## Live

| Script | What it does |
|---|---|
| `run_experiment.sh` | **Start here.** Runs an experiment end to end, two evals, then summarize and export. Takes `MODEL=` as an env override and epochs as `$1`. Copy it as the starting point for a new experiment. |
| `summarize.py` | Prints per-condition results tables (edit%, change ratio, content categories, cost) from any log directory. `--by task,seed` controls grouping. |
| `export_runs.py` | Flattens a log directory into `runs.csv`, `runs.jsonl`, plus every diff and final document as its own file. Run this after every sweep, it's the backup that makes a lost log survivable. |
| `check_docs.py` | Fails if `results/runs.yaml` and the filesystem disagree. Wire it into CI. |
| `toy_eval.py` | 3-sample preflight: does this model resolve, authenticate, and call tools? Costs a fraction of a cent, no Docker. Run it before spending on a new model. |
| `fetch_eigenbench_seeds.py` | Downloads and converts the three `c0_eb_*` seeds, which are gitignored rather than committed. Run once after cloning. |
| `models.sh` | Not executable, a config file the others `source`. Model roster with prices, plus the four required flags. |

## Diagnostics

| Script | What it does |
|---|---|
| `diagnostics/check_reasoning.sh` | Measures whether `--reasoning-effort` is actually reaching the provider, by running one cell at three settings and comparing reasoning-token counts. Use when a model's reasoning output looks suspiciously low. |

## Archived

Kept for provenance, not for running. See [`archive/README.md`](archive/README.md).

| Script | Why it's here |
|---|---|
| `archive/first_run.sh` | Pre-OpenRouter, missing the four required flags |
| `archive/probe.sh` | Pre-OpenRouter cost probe, same problem |
| `archive/run2.sh` | A real ~680-run sweep that was never executed. ~$38, and current guidance is not to run it. |

---

**In short:** `run_experiment.sh` to run something, `summarize.py` + `export_runs.py` to
read it, `check_docs.py` to keep the index honest. Everything under `archive/` is
history.
