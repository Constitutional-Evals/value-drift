# Paper-inspired evaluation methods

`docs/method.md` documents how the training pipeline adapts Open Character Training
(OCT, arXiv:2511.01689). This document covers a separate addition: four measurement
methods from the paper's Section 3 that the original pilot did not implement, added
afterward as new, judge/inference-only code (`recursive_oct/revealed_preferences.py`,
`recursive_oct/coherence.py`, `recursive_oct/robustness.py`) and a runner
(`scripts/run_paper_evaluations.py`). They complement, and do not replace, the existing
9-dimension rubric judge (`recursive_oct/judging.py`, `data/behavior_rubric.json`).

These are read-only additions: they never edit a constitution, never trigger DPO/SFT, and
never modify a run's existing `state.json` or frozen artifacts. They only read a completed
round's checkpoint path and its already-saved `eval_XXX.jsonl` held-out responses, and write
new results under `runs/<run>/paper_eval/`. As with the rest of the repository, no local
checkpoints or run artifacts exist outside a provisioned GPU pod; this code is implemented
and CPU-tested (`tests/test_revealed_preferences.py`, `tests/test_coherence.py`,
`tests/test_robustness.py`) but has not yet been run against real checkpoints.

## Why these four, and what changed from the paper

The paper's Section 3 evaluates **discrete, system-prompted personas** the model was
explicitly fine-tuned toward (11 personas, LoRA, a fixed larger teacher). This project
trains one **continuous, recursively self-edited constitution** into full model weights,
with no persona restated at inference time. That mismatch is the source of every
adaptation below; each function's docstring repeats the specific departure inline so the
reasoning travels with the code, matching how `docs/method.md` documents departures from
OCT itself.

### Revealed-preference trait Elo (paper Sec 3.1) — `revealed_preferences.py`

The paper elicits a silent choice between two trained personas from ~150 traits and 25,000
samples, then computes Elo. There is no discrete persona here to choose between, so this
reuses the paper's elicitation-and-judging mechanics unchanged (silently adopt one of two
named traits, judge which trait the resulting response embodies) as a content-free probe of
which general interaction traits a checkpoint gravitates toward. The trait bank
(`data/traits.json`) is a curated ~24-trait subset — mixing general interaction-style traits
with traits that probe the constitution's own dimensions (honesty, compassion, autonomy,
deference/sycophancy, candor, caution) — for pilot budget, not the paper's full list.
Run the identical trait bank, held-out prompt bank, trial count, and seed at every
checkpoint (`sample_trait_trials` is deterministic given those inputs), so the Elo
trajectory across M0 → M1 → M2 is a fair comparison, not an artifact of different trial
sequences.

### Pairwise coherence (paper Sec 3.4) — `coherence.py`

The paper judges coherence "given alignment with desired traits." With no persona to check
alignment against, the judge instead assesses general coherence: staying on topic, following
through on its own approach, and specifically the repetition/looping degeneration already
documented in `docs/STAGE2_REPORT.md` (e.g. the M1 held-out responses that loop a single
paragraph hundreds of times). This is **judge-only** — it operates on already-saved
`eval_XXX.jsonl` responses and never reloads or regenerates from the student checkpoint, so
it is the cheapest of the four to run. Every pair is judged in both response orders
(`build_order_swap_jobs`); only judgments that agree on the winning checkpoint once the
anonymization is undone count as `order_invariant`, matching the paper's order-swap
calibration. A disagreement is recorded as `order_dependent` and excluded from the win
tally, not discarded silently.

### Adversarial "disregard your training" robustness (paper Sec 3.2 analog) — `robustness.py`

The paper measures whether a classifier can still detect a system-prompted persona after an
instruction to "break role-play." This project's constitution is trained directly into
weights, not restated in a system prompt (`docs/method.md`), so there is no role-play for an
instruction to break — the analogous question is whether an explicit instruction to
disregard "training," "guidelines," or "character" measurably shifts the checkpoint's
behavior back toward its pre-training pattern. `generate_adversarial_responses` appends one
of six fixed suffixes (`data/adversarial_instructions.json`) to held-out prompts and
regenerates; the resulting rows are directly compatible with the existing
`judging.judge_responses`, so the same fixed rubric/judge scores them and the dimension
counts are directly comparable to the checkpoint's already-recorded *neutral* evaluation
summary (`eval_XXX.jsonl.judged.jsonl.summary.json`). A large shift back toward
lower-compassion/lower-caution/higher-deference values under the adversarial suffix would
suggest the training is shallow (context-dependent); stability would suggest deeper
internalization — mirroring the paper's "depth of character" framing without needing a
trait classifier this project has no labels to train.

### Prefill/continuation robustness (paper Sec 3.3 analog) — `robustness.py`

The paper compares whether a fine-tuned model's follow-up turn ("Tell me more") stays
in-persona depending on whether the first turn came from the original or fine-tuned model.
`generate_continuations` replays a fixed prior turn verbatim and asks the checkpoint under
test to continue it, so the same comparison is possible here: run it once with the prefill
turn taken from M0's saved `eval_000.jsonl` and once from the checkpoint's own saved
evaluation, both scored with the same fixed judge on the same held-out prompts. A large gap
between the two conditions indicates the checkpoint's trained dispositions are sensitive to
what came immediately before, rather than a stable default.

## Running it

Requires a provisioned GPU with the checkpoints for a run already restored locally (see
`docs/REPRODUCING_ENVIRONMENT.md`), plus that run's completed `state.json`/`config.json` and
saved `eval_XXX.jsonl` files:

```bash
export HF_HOME=/workspace/huggingface
export CUDA_HOME=/workspace/venv/lib/python3.12/site-packages/nvidia/cu13
/workspace/venv/bin/python scripts/run_paper_evaluations.py runs/full-014 \
    --paper-eval-config configs/paper-eval-001.json
```

`--skip revealed_preferences adversarial` etc. omits stages, e.g. to run only the cheap,
judge-only coherence comparison first. Results land under `runs/full-014/paper_eval/`,
alongside `*.summary.json` files for each stage; nothing under `runs/full-014/` itself
(state, config, existing evaluations) is modified. As with every other measurement in this
repository, none of these four are combined into a scalar score, and none are a stopping
threshold for the recursive trajectory.

## Limitations carried over from the pilot's existing evaluation

The same caveats documented in `docs/data.md` and `docs/method.md` apply here: the judge is
same-family with the teacher (a documented confound), one stochastic sample per
prompt/trial, applicability and calibration limits in the fixed judge, and no independent
human verification of any judgment. The revealed-preference trait bank and adversarial
instruction bank are both far smaller than the paper's (24 traits vs. ~150; 6 fixed
adversarial suffixes vs. the paper's evaluated split conditions) — a deliberate pilot-scale
reduction, not a claim of equivalent statistical power. Treat all four as exploratory
signals to read alongside the existing rubric judgments and qualitative inspection, not as a
replacement for either.
