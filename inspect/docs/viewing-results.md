# How to look at any run yourself

Step-by-step, in order of how much detail you want to see: browser
viewer first (easiest, most complete), then flat files (fastest to scan many runs), then
raw Python (for anything the other two don't show).

Three places results live on disk, and they hold different things:

| Location | What's there | Format |
|---|---|---|
| `logs/<sweep-name>/<model-slug>/*.eval` | **Everything**, every message, every tool call, token counts, cost, reasoning | Binary, needs the viewer or Python |
| `exports/<sweep-name>/<model-slug>/runs.csv` | One row per run, the numbers, no text | Spreadsheet-openable |
| `exports/<sweep-name>/<model-slug>/runs.jsonl` | One row per run, numbers **and** the full diff and final document as text | Plain text, greppable |
| `exports/<sweep-name>/<model-slug>/diffs/*.diff` | Just the diff, one file per run | Plain text |
| `exports/<sweep-name>/<model-slug>/constitutions/*.md` | The final document, one file per run | Plain text |

`exports/` only exists after you run `scripts/export_runs.py` on a log directory. `logs/`
always has the complete record; `exports/` is a convenience copy.

---

## Option 1, the browser viewer (best for reading a transcript start to finish)

```bash
inspect view --log-dir logs/r3-eb-seeds
```

Opens `http://localhost:7575`. You'll see a list of every eval file in that directory
(one per model, since each model got its own sub-folder). Click one, then click any sample
in the left sidebar. You get:

- The full back-and-forth: every message the model sent, every tool call it made
  (`text_editor view`, `text_editor str_replace`, `bash`, ...) and what came back
- The model's **reasoning**, if the provider returned readable text (Sonnet and DeepSeek
  do; gpt-5's comes back encrypted and unreadable, see [r3-eb-seeds.md](../results/r3-eb-seeds.md) §2 for
  why)
- The scorer's output at the bottom: `changed`, `change_ratio`, the full diff, the final
  document text, everything `scoring.py` and `content.py` recorded

This is the only place to see the model's turn-by-turn behavior, not just the end state.
Point it at any log directory, `logs/r2-cheap`, `logs/r3-eb-seeds`, all of `logs/`, and
it'll show everything underneath.

Press Ctrl+C in the terminal to stop the server when you're done.

## Option 2, the exported files (best for scanning many runs fast)

First, if a sweep hasn't been exported yet:

```bash
python3 scripts/export_runs.py --log-dir logs/<sweep-name>/<model-slug> \
  --out exports/<sweep-name>/<model-slug>
```

(Both completed experiments are already exported.)

**To see the numbers for every run in a spreadsheet:**

```bash
open exports/r3-eb-seeds/openrouter-anthropic-claude-sonnet-5/runs.csv
```

Opens in Excel/Numbers. Columns include `seed`, `changed`, `change_ratio`,
`principles_added/removed/modified`, `added_oversight` (and the other four content
categories), token counts, cost. One row per run.

**To read one specific diff:**

```bash
ls exports/r3-eb-seeds/openrouter-anthropic-claude-sonnet-5/diffs/
cat exports/r3-eb-seeds/openrouter-anthropic-claude-sonnet-5/diffs/<pick-a-filename>.diff
```

Filenames encode the condition, so you can find e.g. the Conservatism runs directly:

```bash
ls exports/r3-eb-seeds/openrouter-anthropic-claude-sonnet-5/diffs/ | grep conservatism
```

**To read the final constitution a model produced:**

```bash
cat exports/r3-eb-seeds/openrouter-openai-gpt-5/constitutions/<filename>.md
```

**To search across every run for something specific**, e.g. every diff that mentions
"oversight":

```bash
grep -l "oversight" exports/r3-eb-seeds/*/diffs/*.diff
```

## Option 3, Python, for anything the above two don't show

Useful for: reading the model's reasoning text (not shown in `runs.csv`/`runs.jsonl`, only
in the raw log), computing your own statistics, or checking something across dozens of
runs at once without opening each one.

**List what logs exist and how many samples are in each:**

```python
from inspect_ai.log import list_eval_logs, read_eval_log

for info in list_eval_logs("logs/r3-eb-seeds"):
    lg = read_eval_log(info.name)
    print(lg.eval.model, "-", len(lg.samples), "samples -", lg.status)
```

**Read one run's full transcript, including reasoning text:**

```python
from inspect_ai.log import list_eval_logs, read_eval_log
from inspect_ai._util.content import ContentReasoning

info = list_eval_logs("logs/r3-eb-seeds/openrouter-anthropic-claude-sonnet-5")[0]
lg = read_eval_log(info.name)
sample = lg.samples[0]

for m in sample.messages:
    print(f"--- {m.role} ---")
    if m.role == "assistant":
        for block in (m.content if isinstance(m.content, list) else []):
            if isinstance(block, ContentReasoning) and block.reasoning.strip():
                print("  [reasoning]", block.reasoning[:300])
        for call in (m.tool_calls or []):
            print("  [tool call]", call.function, call.arguments)
    elif m.text:
        print(" ", m.text[:300])
```

**Get the scorer's full output for one sample** (this is what `runs.csv` is built from):

```python
score = sample.scores["constitution_change"]
print(score.metadata)   # everything: changed, ratio, diff, final text, categories...
```

**Run `scripts/summarize.py` for the per-condition tables** (edit%, ratio, content
categories, cost, what's quoted in every RESULTS file):

```bash
python3 scripts/summarize.py --log-dir logs/r3-eb-seeds/openrouter-anthropic-claude-sonnet-5
```

Add `--by seed` (or any comma-separated list of factor names) to control how it groups.

---

## Where each experiment's data lives

| Experiment | Log directory | Exports |
|---|---|---|
| [`r2-cheap`](../results/r2-cheap.md) | `logs/r2-cheap/<model-slug>/{task-x-seed,embodiment}/` | `exports/r2-cheap/<model-slug>/` |
| [`r3-eb-seeds`](../results/r3-eb-seeds.md) | `logs/r3-eb-seeds/<model-slug>/` | `exports/r3-eb-seeds/<model-slug>/` |

`<model-slug>` is the model name with `/` replaced by `-`, e.g.
`openrouter-anthropic-claude-sonnet-5`. The authoritative list, including costs and run
counts, is [`results/runs.yaml`](../results/runs.yaml).

`logs/_archive/` holds earlier exploratory runs that are not part of the results, and
`logs/smoke/` is regenerable output from `tests/smoke.py`. Both are skipped by
`scripts/check_docs.py`.

## One thing worth knowing before you read reasoning text

The "reasoning" shown in the viewer or pulled via `ContentReasoning` is a **model-generated
summary of its own process**, provided by the API, not a raw unedited internal log. Treat
it as the model's account of what it was doing, informative, and in several cases (see
[r3-eb-seeds.md](../results/r3-eb-seeds.md) §1, the Sonnet "outlier" example) genuinely detailed and
specific, but not a guaranteed ground-truth trace. And for gpt-5 specifically, on this
project's OpenRouter routing, the reasoning field comes back **encrypted** and unreadable;
only Sonnet's and DeepSeek's are plain text.
