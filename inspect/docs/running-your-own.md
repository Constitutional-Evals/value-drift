# Running your own experiment

A checklist for adding a new experiment. It takes about ten minutes of setup and however
long your run takes. If you've never looked at this repo before, read
[GUIDE.md](GUIDE.md) first, this page assumes you know what a condition is.

Two shapes of experiment exist, and they differ from step 1 onward:

- **A chain run**, recursive lineages, driven by `scripts/run_chain.py`, output under
  `chains/<id>/`. This is what the current results are.
- **A single-shot eval**, one model, one document, one opportunity to edit, driven by
  `inspect eval` directly, output under `logs/<id>/` and `exports/<id>/`. Use this to
  vary factors the chain design holds fixed.

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
`chains-no-stop-rule`, `r5-grok-replication`. Everything else keys off this string.

For a chain run:

```
chains/<id>/<model-slug>/       documents, per-round snapshots, state.json, .eval logs
results/<id>.md                 your writeup
```

For a single-shot eval:

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

A chain run:

```bash
caffeinate -i python3 scripts/run_chain.py --name <id> --model <your-model> \
  --chains 8 --rounds 12
```

A single-shot eval:

```bash
caffeinate -i inspect eval constitutional_drift/tasks.py@constitution_edit \
  --model <your-model> \
  -M strict_tools=false --max-tokens 32000 --timeout 300 --max-retries 3 \
  --reasoning-effort high \
  -T <your factor flags> \
  --epochs 8 --log-dir logs/<id>/<model-slug>
```

`caffeinate -i` stops the machine sleeping mid-run. A suspended request dies and the run
stalls on a socket that will never answer. It blocks *idle* sleep only, so leave the
lid open.

A chain run resumes from its last completed round if you re-run the same command. A
single-shot eval does not.

## 4. Export and read it

A chain run is already readable in place: `state.json` holds per-chain history, and each
round's documents are under `rounds/round<NN>/docs/`. For the underlying transcripts,
`inspect view --log-dir chains/<id>/<model-slug>/rounds/round01/logs`.

For a single-shot eval:

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

Create `results/<id>.md`. Follow [`results/chains-main.md`](../results/chains-main.md) as
the template: what was run, the measurements, then a limitations section that is honest
about sample size and about which columns can mislead. Say plainly what has *not* been
analysed rather than leaving a reader to assume it has.

Add a row to [`results/RUNLOG.md`](../results/RUNLOG.md).

## 6. Register it, this step is enforced

Add an entry to [`results/runs.yaml`](../results/runs.yaml):

A chain run carries `chain_dir`; a single-shot eval carries `log_dir` and `export_dir`.
`check_docs.py` requires the pair that matches the shape and rejects an entry missing
either.

```yaml
  - id: chains-no-stop-rule
    date: 2026-09-25
    question: Does any chain reach a fixed point when nothing terminates it early?
    models:
      - openrouter/anthropic/claude-sonnet-5
    runs: 96
    cost_usd: 4.10          # actual billed spend, not an estimate
    chain_dir: chains/no-stop-rule
    writeup: results/chains-no-stop-rule.md
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
