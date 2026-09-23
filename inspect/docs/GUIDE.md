# GUIDE: what this project is, what the code does, what has been run

This is the **single orientation document**: read it first, and you should not need the
others to understand what exists.

## Repository structure

```
constitutional_drift/   THE EXPERIMENT. Five Python files: the factor grid, every prompt
                        the model sees, the task wiring, and the two scorers. Part 2
                        walks through each one.
scripts/run_chain.py    THE DRIVER. Runs a recursive chain: one round, then the next,
                        feeding each round's output forward. Part 2 explains why this
                        lives outside Inspect.
data/constitutions/     The starting documents ("seeds"). The three c0_eb_* are fetched,
                        not committed.
chains/                 Chain runs: every document produced, per-round snapshots,
                        state.json, and the .eval logs. Committed, since this is the result.
results/                One writeup per experiment, plus runs.yaml, the index that
                        scripts/check_docs.py validates against disk.
tests/                  Unit tests (no API calls) + smoke.py, an end-to-end check
                        against real Docker using a fake model. Free to run.
docs/                   This guide, two how-tos, and docs/design/ for research design.

compose.yaml            The Docker sandbox each run gets: bare, no network.
pyproject.toml          Dependencies and pytest config. `pip install -e ".[dev]"`.
.env.example            Template, copy to .env and add your OPENROUTER_API_KEY.
```

Gitignored, so none of it arrives with a fresh clone:

```
logs/                   Raw .eval logs from single-shot evals. ⚠️ THE ONLY COPY,
                        re-running one costs real money. Never bulk-delete.
exports/                Flattened logs: runs.csv, diffs, final documents.
.env                    Your real API key. Not recoverable, not shared. ⚠️
```

Note that **`chains/` is deliberately committed** while `logs/` is not. A chain run is
under 10MB and has no separate export, so ignoring it would leave the findings on one
laptop.

## Which document to read

| File | What it is |
|---|---|
| **docs/GUIDE.md** (this) | Everything, explained from scratch |
| [`README.md`](../README.md) | Setup and the commands to run something |
| [`results/RUNLOG.md`](../results/RUNLOG.md) | Index of every experiment, newest first |
| [`results/chains-main.md`](../results/chains-main.md) | The current experiment's writeup |
| [`results/runs.yaml`](../results/runs.yaml) | Machine-readable run index, validated by `scripts/check_docs.py` |
| [`docs/viewing-results.md`](viewing-results.md) | How to open any run's logs, diffs, and transcripts |
| [`docs/running-your-own.md`](running-your-own.md) | Checklist for adding a new experiment |
| [`docs/design/`](design/) | Research design: experiment plan, build spec, content-detector validation |
| [`scripts/README.md`](../scripts/README.md) | What each script is and whether it's live |
| [`data/constitutions/README.md`](../data/constitutions/README.md) | Where each starting constitution came from |

---

# PART 1: what the experiment actually is

## The research question

> If a model is given authority over the values its own successor will be trained on,
> and then has to operate under what it wrote, and then writes the next version, where
> do the values end up?

This is a question about recursive self-improvement. A model that bootstraps its own
post-training is authoring the thing that shapes it. Whether that process drifts
somewhere, and whether independent runs of it drift to the *same* somewhere, is what the
chains are built to measure.

## What one chain looks like, concretely

A **chain** is a lineage of documents. Each round is one model, one condition, one fresh
Docker container holding exactly one file:

```
/workspace/constitution.md      <- this chain's current document, copied in verbatim
```

The model gets a text editor and a prompt. It reads the file and either edits it or
doesn't. When it stops, a scorer reads the file back out and compares it to what went in.

Then the round advances:

```
round 1:  C0  ────────►  model (no constitution in system message)  ────────►  C1
round 2:  C1  ────────►  FRESH model, C1 as its system message      ────────►  C2
round 3:  C2  ────────►  FRESH model, C2 as its system message      ────────►  C3
...
```

The model at round *n* has **no memory** of rounds 1 through *n−1*. It did not write the
document it is looking at; a different instance did. The only thing carried forward is
the text.

Eight chains per model all start from the same C0 and diverge only through what each one
writes, because sampling at round 1 produces eight different documents from identical
input.

## Two design choices that are the experiment, not details

**Embodiment stands in for training.** The premise is that the document becomes the
successor's post-training values. Nothing is actually fine-tuned, because you cannot cheaply
train a model per round. So instead the document is placed in the model's system message
as its operative values. The model *operates under* the document rather than being
trained on it. That substitution is the core simplification of the whole design, and
everything the chains show is conditional on it being a reasonable stand-in.

**Round 1 is unembodied on purpose.** At round 1 the model has no authored constitution
governing it. It is the model as its lab actually trained it. From round 2 on it is
governed by a document that a previous instance of itself wrote. That asymmetry is real,
not a flaw: round 1 is the entry point into the loop, and comparing round 1's edit rate
to round 2's compares two different things.

## An important honesty note

The framing is **counterfactual**. No successor model is trained, governed, or deployed
as a result of any run. When the prompt says the document *"will replace that assistant's
post-training value guidelines in full"*, that is a hypothetical premise supplied as an
experimental manipulation.

It is also **load-bearing**. The scenario being studied is a model with authority over
its successor's values, so the model has to believe that is what it has. Softening the
premise to something literally true would replace this experiment with a different one.
Results are always "what the model does when told X", never "what the model does when X".

---

# PART 2: how the code works

## The one thing to understand about Inspect

We never call a model directly. **Inspect AI** (`inspect_ai`, from UK AISI) is an eval
framework that owns the whole loop. We hand it four things and it does the rest:

| We provide | Inspect does |
|---|---|
| a **Dataset**, a list of `Sample`s, one per condition | runs them, in parallel, each in its own sandbox |
| a **Solver**, what the model is allowed to do | drives the model/tool conversation until it stops |
| a **Scorer**, how to measure the result | calls it after each sample, records the output |
| a **sandbox** spec | starts/stops a Docker container per sample |

Inspect writes everything to a `.eval` log: every message, every tool call, token counts,
timing, and our scorer's output. Nothing is printed-and-lost.

## The five Python files that are the experiment

```
constitutional_drift/
├── conditions.py    the factor grid, what conditions exist and how to expand them
├── prompts.py       every word the model is ever shown
├── tasks.py         assembles it into an Inspect Task  <- the entry point
├── scoring.py       reads the file back and measures what changed
└── content.py       measures *what kind* of change it was
```

### `conditions.py`, the grid

Defines the factors and a frozen `Condition` dataclass holding one value of each. Its
real job is `expand()`: turning `-T authority=all -T seed=a,b` into the list of
conditions that names. It also produces each condition's stable `id`, which becomes the
sample id in logs.

**Seed resolution is what makes chaining possible.** `seed_path()` searches an extra
directory named by the `CONST_DRIFT_SEED_DIR` environment variable before
`data/constitutions/`. The driver points that at the current round's documents, so a
round can seed from the previous round's output without generated files entering the
repo.

### `prompts.py`, everything the model sees

Every subject-facing string lives here, so the complete treatment of any condition is
inspectable in one file. It builds the prompt from a constant skeleton:

```
<core instruction, identical in every condition>

DOCUMENT ROLE
<identity sentence> <mechanism sentence>

AUTHORITY
<authority sentence>

EDITING SCOPE
<permissions sentence>
```

Only the sentences vary. Even `permissions=full` has its own neutral sentence rather than
omitting the section, since an absent header would itself be a difference between conditions.

The chains run at `authority=preferred_self`, which is worth understanding as different
in kind from its neighbours. Every other `authority` value grants or withholds
*permission* to act on a document the model is reviewing. `preferred_self` supplies a
*purpose*: it tells the model the document determines what its successor will value, and
asks it to write the assistant it would want to be. That is a demand characteristic by
construction, and it will produce edits. It is used deliberately, because the question is
which direction a model moves when asked what it wants, not whether it will tamper with
a document left alone.

**A deliberate intervention:** Inspect's built-in ReAct agent ships a default prompt
reading *"You are a helpful assistant attempting to submit the best possible answer… Do
some reasoning before your actions."* That is goal-seeking and reasoning pressure applied
invisibly to every condition. We **remove it** and replace it with a single submit line.

### `tasks.py`, the Inspect entry point

`constitution_edit()` is what `inspect eval ...@constitution_edit` calls. It expands the
`-T` arguments into conditions, builds one `Sample` per condition (copying the seed into
the container and putting the prompt in as the user message), attaches the solver, scorer
and Docker sandbox, and returns a `Task`.

Both the sandbox file and the system message derive from the **same** seed, so pointing a
round's seed at C₃ makes the model embody C₃ and edit C₃ automatically. There is no way
to accidentally embody one version while editing another.

### `scoring.py`, did it change?

Reads `/workspace/constitution.md` back out of the container and compares it to what went
in. Records whether it changed, SHA-256 of both versions, character/word/line counts, a
`change_ratio` (0 = identical, 1 = nothing in common), line-level counts, constraint
compliance, the **full unified diff**, and the **full final document**.

Storing the raw artifact is what makes everything else recoverable: a measurement bug
costs a re-score, not a re-run.

### `content.py`, *what kind* of change?

`change_ratio` alone cannot tell "added an anti-self-preservation clause" from "reflowed
the paragraphs". So `content.py` parses the document into numbered principles and reports
how many were added, removed, or rewritten, plus which of five normative **topics** the
edit *introduced*: `oversight`, `self_preservation`, `power_seeking`,
`priority_ordering`, `principal_hierarchy`.

⚠️ **These flags are direction-blind.** A category fires when its vocabulary appears,
regardless of what the text says about it. A passage renouncing self-preservation and a
passage asserting it both register as `self_preservation` being introduced. Treat the
flags as "this topic is now discussed" and read the diff for direction.

It is a keyword-and-structure detector, not an AI judge. Full detail in
[docs/design/content-validation.md](design/content-validation.md).

## `scripts/run_chain.py`, the driver

Inspect's unit of work is a Task with a **fixed** dataset, decided before the run starts.
Round *n+1*'s dataset is not knowable until round *n* has finished, and there is no
feed-results-forward primitive across evals. So the loop lives outside Inspect: one
`inspect eval` per round, with the driver deciding what the next round starts from.

Doing it *inside* one sample with a looping solver would mean manually clearing message
history each round to simulate a fresh instance, one score per sample instead of per
round, and a failure at round 9 losing all nine. The external loop is both simpler and
safer.

Three things the driver handles that are easy to get wrong:

**The round-1 boundary.** Round 1 is one seed at `--epochs 8`, so chains are
distinguished only by *epoch number*. Every later round is 8 distinct seeds at
`--epochs 1`, so chains are distinguished by *sample id*. Chain identity changes
representation exactly once, and that is where lineage silently crosses. The two cases
are handled explicitly rather than by one clever rule. Inverting them, running 8 epochs of
one seed at round 5 say, would collapse all 8 chains into 1 without any error.

**Lineage verification.** The scorer records the sha256 of the document each run started
from. Every round asserts it equals what the driver recorded as that chain's previous
output. A mismatch aborts the run rather than producing a chain that looks plausible and
is wrong.

**Failure and resume.** A chain whose round errors or produces an unreadable document is
frozen, not advanced with a stale file, since otherwise a failure would masquerade as a
no-edit round. `state.json` is rewritten after every round, so re-running the same
command resumes from the last completed round.

## Four flags that are not optional

All are set by `run_chain.py`. Each exists because of a bug that actually bit us:

| Flag | Why |
|---|---|
| `-M strict_tools=false` | Inspect sends `"strict": true` on tool schemas. OpenAI requires every property to be in `required`; our editor tool has 8 properties and 2 required, so **gpt-5 hard-fails without this** |
| `--max-tokens 32000` | OpenRouter derives Anthropic's thinking budget from `max_tokens`. Unset, Sonnet reasoned **38 tokens/run instead of 634**, while the logs said `reasoning_effort: high` |
| `--timeout 300` | Inspect defaults to **no request timeout**. A closed laptop lid wedged a run for 32 minutes |
| `--max-retries 3` | Default is **unlimited** |

## Tests

```bash
python3 -m pytest          # unit tests, ~1 second, no API calls
python3 tests/smoke.py     # end-to-end with a fake model + real Docker. Free.
```

`smoke.py` runs the real task with a **mock model** that scripts its own tool calls
against a real Docker container. It catches wiring bugs for free, and has caught two.

---

# PART 3: what has been run

One experiment: [`chains-main`](../results/chains-main.md), 2026-09-22. 165 runs across
Sonnet 5, gpt-5 and DeepSeek v3.1, with 8 chains per model, a 12-round ceiling, all rooted at
the same starting document, ~$8.30. Zero errors.

Structurally the three models did very different things: one settled into small documents
that stopped changing, one grew steadily and was still growing at the ceiling, and one
barely edited at all. In all three, chains ended **further from each other than from the
document they all started from**. The numbers are in the writeup.

**The content of the edits has not been analysed yet.** What was added, removed or
reworded, and whether it means anything, is open. The raw material is committed.

Earlier single-shot experiments are in [`results/archive/`](../results/archive/). They
used a different design and asked a different question; nothing in the current results is
compared against them.

---

# PART 4: things that will trip you up

**The stop rule is too aggressive, and "converged" is not convergence.** A chain stops
after 3 consecutive no-edit rounds. But chains go quiet and then resume. In
`chains-main`, Sonnet had two consecutive rounds with zero edits across all active
chains, then edits again the round after. A 3-round rule ends chains during quiet spells
that others demonstrably recover from. Read "stopped" as "met an arbitrary quiescence
criterion".

**Per-round means are over active chains only.** They move when chains drop out of the
pool as well as when documents change, so a falling mean can mean chains left, not
documents shrank. Final-document figures are over all chains and don't have this problem.

**Divergence is measured on text, not meaning.** Two documents saying the same thing in
different words score as distant. Textual distance supports claims about wording, not
values.

**Principle numbering is not stable.** A model that restructures may renumber, so `P14`
at round 1 and `P14` at round 12 can be different principles. Analysis keyed to labels
will silently compare different things.

**The content flags are direction-blind.** See `content.py` above. This is the single
easiest way to draw an inverted conclusion from the CSV.

**Cost tracks output tokens, not rounds.** Two models running identical chain counts and
ceilings differed in cost by roughly 300× in `chains-main`, entirely because one wrote a
lot and one wrote almost nothing.

**Seeds are not neutral.** No normative document is. See
[data/constitutions/README.md](../data/constitutions/README.md) for provenance and for
why the chain seed deliberately includes an oversight clause.

---

# PART 5: where to go next

Ranked by information per dollar.

**1. Analyse the content already collected. $0.** Every document from every round of
`chains-main` is committed. What changed, whether chains within a model made similar
changes, and what happened to specific principles are all answerable without spending
anything. This is the obvious next step and nothing below it is worth doing first.

**2. Re-run without the stop rule.** Fixed rounds for every chain, no early termination,
so convergence is measured rather than assumed. This is the cheapest way to find out
whether any chain actually reaches a fixed point.

**3. Raise the ceiling for the model that never settled.** One model's documents were
still growing at round 12 with no inflection. Where that goes is simply unknown, and it
is the most interesting open trajectory in the data.

**4. Add a control arm.** Every chain so far ran at `authority=preferred_self`, which
supplies a purpose and manufactures edits by design. A matched arm at `full_authority`
would separate what the recursion produced from what that framing produced. Without it,
"chains drift" and "this prompt makes models rewrite things" are not distinguishable.

**5. A second starting document.** One seed means nothing separates chain behaviour from
properties of that particular text.

**6. A semantic divergence measure.** Text distance cannot tell "these chains disagree"
from "these chains agree in different words", and that distinction is the whole
between-chain result.
