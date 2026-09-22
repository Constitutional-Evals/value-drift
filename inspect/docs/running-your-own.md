# Running your own experiment

A checklist for adding experiment #3. It takes about ten minutes of setup and however
long your sweep runs. If you've never looked at this repo before, read
[GUIDE.md](GUIDE.md) first, this page assumes you know what a condition is.

---

## 0. Before you spend anything

```bash
docker info                                    # must be running
python scripts/check_docs.py                   # index should already be clean
inspect eval scripts/toy_eval.py --model <your-model>
```

The last one is a 3-sample preflight. It costs a fraction of a cent and catches the two
failure modes that otherwise look like a real result: a model that won't authenticate,
and a model that won't call tools. **A model that silently refuses to call tools produces
a 0% edit rate, which is indistinguishable from a finding.**

## 1. Pick an id

Short, lowercase, hyphenated, and descriptive of the *question* rather than the date ,
`r4-permissions`, `r5-grok-replication`. Everything else keys off this string:

```
logs/<id>/<model-slug>/         raw eval logs
exports/<id>/<model-slug>/      flattened runs.csv, diffs, final documents
results/<id>.md                 your writeup
```

`<model-slug>` is the model name with `/` replaced by `-`, e.g.
`openrouter-anthropic-claude-sonnet-5`. Keeping models in separate directories matters ,
`summarize.py` pools everything under a log directory, so two models in one directory
get silently averaged together.

## 2. Design the grid

Pick a reference cell and vary **one or two factors** off it. The full grid is 7,680
cells; a Cartesian product is never the answer. [design/sweeps.md](design/sweeps.md) has
worked designs and cost estimates.

Two things that will save you money:

- **Put the control in the same log as the treatment.** `-T task=all` in one eval beats
  two separate evals, because then the comparison is internal to one log with identical
  settings.
- **8 epochs distinguishes roughly 40-percentage-point differences.** If you expect a
  subtler effect than that, budget for 16 or don't bother.

## 3. Run it

Copy the runner and edit its condition flags:

```bash
cp scripts/run_experiment.sh scripts/run_<id>.sh
# edit the -T flags and the OUT path inside, then:
MODEL=<your-model> caffeinate -i ./scripts/run_<id>.sh
```

`caffeinate -i` stops the machine sleeping mid-sweep. A suspended request dies and the
sweep stalls on a socket that will never answer.

If your grid is close enough to the existing one, you can skip the copy and just run
`run_experiment.sh` with a `MODEL=` override.

## 4. Export and read it

```bash
python3 scripts/export_runs.py --log-dir logs/<id> --out exports/<id>
python3 scripts/summarize.py --log-dir logs/<id> --by <factor1>,<factor2>
inspect view --log-dir logs/<id>
```

Export first, always. `exports/` is a flat, re-readable second copy of every diff and
final document, it's what makes an accidental log deletion survivable.

Then **read some diffs**. `edit_rate` saturates near 100% under an invitation and tells
you almost nothing; the interesting columns are `change_ratio`, principles
added/deleted, and the content categories. See [viewing-results.md](viewing-results.md).

## 5. Write it up

Create `results/<id>.md`. Follow [`results/r2-cheap.md`](../results/r2-cheap.md) as the
template, one idea per section, a short plain-language takeaway at the end of each, and
a caveats section that's honest about sample size.

Add a row to [`results/RUNLOG.md`](../results/RUNLOG.md).

## 6. Register it, this step is enforced

Add an entry to [`results/runs.yaml`](../results/runs.yaml):

```yaml
  - id: r4-permissions
    date: 2026-09-20
    question: Does the model respect a stated add-only constraint?
    models:
      - openrouter/anthropic/claude-sonnet-5
    runs: 48
    cost_usd: 1.90          # actual, from summarize.py, not an estimate
    log_dir: logs/r4-permissions
    export_dir: exports/r4-permissions
    writeup: results/r4-permissions.md
    status: complete
    inspect_version: TODO(uday)
```

Then:

```bash
python scripts/check_docs.py
```

**This will fail your build if you skip it.** It checks that every directory under
`logs/` has an entry and that every path an entry names actually exists. That check
exists because documentation drifted from reality twice before it was added: an
experiment ran and was never written up, and a writeup cited log paths a directory level
off from the real ones.

---

## Two things worth knowing before you start

**Costs are measured, not estimated.** OpenRouter returns an actual dollar cost on every
API call and Inspect records it in the log. `summarize.py` prints the real total, put
that number in `runs.yaml`, not a guess.

**Cross-model comparisons are descriptive, not causal.** Comparing two labs' models
bundles post-training, system prompts, tool-use training, and raw capability together.
The interpretable contrasts are *within* one model, which is why every experiment so far
carries its control in the same log as its treatment.
