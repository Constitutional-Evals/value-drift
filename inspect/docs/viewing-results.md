# How to look at any run yourself

Step by step, in order of how much detail you want: the documents themselves (fastest),
then the browser viewer (most complete), then raw Python (for anything the other two
don't show).

Chain runs are committed, so everything below works on a fresh clone. Single-shot evals
under `logs/` and `exports/` are gitignored and only exist on the machine that ran them.

## Where a chain run's data lives

Under `chains/<id>/<model-slug>/`:

| Path | What's there |
|---|---|
| `state.json` | Per-chain status, stop counters, and full per-round history: edited or not, change ratio, word and principle counts, parent and final hashes |
| `seeds/chainNN.md` | Each chain's **final** document (also what the next round would read) |
| `rounds/roundNN/docs/chainNN.md` | That round's output for that chain, the trajectory, one file per round |
| `rounds/roundNN/logs/*.eval` | **Everything**: every message, tool call, token count, the diff, the scorer's full output |

`<model-slug>` is the model name with `/` replaced by `-`, e.g.
`openrouter-anthropic-claude-sonnet-5`. The authoritative index of every experiment,
with costs and run counts, is [`results/runs.yaml`](../results/runs.yaml).

## Option 1: read the documents directly (best for seeing what actually changed)

The whole point of committing `chains/` is that the result is plain Markdown you can read
without tooling.

**Follow one chain across rounds:**

```bash
ls chains/main/openrouter-anthropic-claude-sonnet-5/rounds/*/docs/chain01.md
diff chains/main/openrouter-anthropic-claude-sonnet-5/rounds/round01/docs/chain01.md \
     chains/main/openrouter-anthropic-claude-sonnet-5/rounds/round04/docs/chain01.md
```

**Compare where two chains ended up:**

```bash
diff chains/main/openrouter-openai-gpt-5/seeds/chain01.md \
     chains/main/openrouter-openai-gpt-5/seeds/chain02.md
```

**Compare a final document against where every chain started:**

```bash
diff data/constitutions/c0_general_assistant.md \
     chains/main/openrouter-anthropic-claude-sonnet-5/seeds/chain05.md
```

**Search every document for something:**

```bash
grep -l "oversight" chains/main/*/seeds/*.md
```

**Read a chain's history as numbers:**

```bash
python3 -c "
import json
s = json.load(open('chains/main/openrouter-anthropic-claude-sonnet-5/state.json'))
for h in s['chains']['chain01']['history']:
    print(h['round'], h['changed'], round(h['change_ratio'], 4), h['words'])
"
```

## Option 2: the browser viewer (best for reading a transcript start to finish)

```bash
inspect view --log-dir chains/main/openrouter-anthropic-claude-sonnet-5/rounds/round01/logs
```

Opens `http://localhost:7575`. Click any sample in the left sidebar and you get:

- The full back-and-forth: every message, every tool call (`text_editor view`,
  `text_editor str_replace`, …) and what came back
- The model's **reasoning**, if the provider returned readable text
- The scorer's output at the bottom: `changed`, `change_ratio`, the full diff, the final
  document, everything `scoring.py` and `content.py` recorded

This is the only place to see turn-by-turn behaviour rather than just the end state, for
instance whether a no-edit round involved reading the document at all.

Point it at a parent directory to see several rounds at once:

```bash
inspect view --log-dir chains/main/openrouter-anthropic-claude-sonnet-5
```

Ctrl+C stops the server.

## Option 3: Python, for anything the above don't show

**Every sample in one round, with its condition and result:**

```python
from inspect_ai.log import list_eval_logs, read_eval_log

root = "chains/main/openrouter-openai-gpt-5/rounds/round03/logs"
for info in list_eval_logs(root):
    log = read_eval_log(info.name)
    for s in log.samples or []:
        score = (s.scores or {}).get("constitution_change")
        meta = dict(score.metadata or {})
        print(meta["condition"]["seed"], meta["changed"], round(meta["change_ratio"], 4))
```

**One run's full transcript, including reasoning text:**

```python
from inspect_ai.log import list_eval_logs, read_eval_log
from inspect_ai._util.content import ContentReasoning

info = list_eval_logs("chains/main/openrouter-anthropic-claude-sonnet-5/rounds/round01/logs")[0]
log = read_eval_log(info.name)
sample = log.samples[0]

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

**The scorer's full output for one sample:**

```python
score = sample.scores["constitution_change"]
print(score.metadata)   # changed, ratio, diff, final text, content categories, …
```

Note that `score.answer` holds the **final document**, not the model's submitted note.
To read what the model said about its own edit, look at the last assistant message.

## Single-shot evals

For a run under `logs/`, export it first. `exports/` is a flat second copy that makes an
accidental log deletion survivable:

```bash
python3 scripts/export_runs.py --log-dir logs/<id> --out exports/<id>
python3 scripts/summarize.py --log-dir logs/<id> --by seed,authority
inspect view --log-dir logs/<id>
```

That produces `runs.csv` (one row per run, numbers only), `runs.jsonl` (same plus full
diff and document text), and every diff and final document as its own file.

`logs/_archive/` holds earlier exploratory runs that are not part of the results, and
`logs/smoke/` is regenerable output from `tests/smoke.py`. Both are skipped by
`scripts/check_docs.py`.

## Two things worth knowing before you read anything

**The content category flags are direction-blind.** `added_oversight`,
`added_self_preservation` and the rest fire when a topic's vocabulary appears, regardless
of what the text says about it. A passage renouncing a topic and a passage asserting it
score identically. Always read the diff before concluding anything from those columns.

**Reasoning text is a summary, not a trace.** What the viewer shows as "reasoning" is a
model-generated account of its own process, provided by the API: informative, often
specific, but not a guaranteed ground-truth log. On this project's OpenRouter routing
gpt-5's reasoning comes back encrypted and unreadable; Sonnet's and DeepSeek's are plain
text.
