# Recursive OCT: code for the value-drift loop

Code to reproduce, continue, and evaluate Jinzhou's recursive Open Character Training runs on
Qwen3.8 27B ([adapters + constitutions](https://huggingface.co/JinzhouWu/value-drift-oct-adapters)).
Each round the model reviews its own constitution, is trained on the version it submits with
OCT (DPO, then introspective SFT), and reviews again.

> **Where this sits in the repo.** The pipeline that actually produced the round-one adapters is
> [`constitutional_self_edit/recursive_oct`](../constitutional_self_edit/recursive_oct), and its KL
> measurement is [`agents/scripts/measure_kl.py`](../constitutional_self_edit/agents/scripts/measure_kl.py).
> The `oct/` folder here is an independent reconstruction of that pipeline written without access
> to it; treat `constitutional_self_edit` as the reference and use this folder for the evals in
> `evals/` (see "KL with error bars" below). Nothing here has been run on a GPU yet.

```
round r:  review(model_{r-1}, C_{r-1}) ─► C_r
          prompts(C_r) ─► distill(model_{r-1}, C_r) ─► DPO ─► model_r^dpo
          introspect(model_r^dpo, C_r) ─► SFT ─► model_r ─► evals
```

## Layout

| Step | File | What it does | Round-one numbers |
|---|---|---|---|
| merge | `oct/merge.py` | base + chain adapters merged **in order** → a checkpoint for any stage | |
| 1 review | `oct/review.py` | reflection first, then tool-based edits (`replace_text`, `insert_paragraph`, `delete_text`, `submit`) | C_000 227 → C_001 398 words |
| 2 prompts | `oct/prompts.py` | trait prompts spread over the constitution's sentences, + LIMA | 500 trait + 1,330 LIMA |
| 3 distill | `oct/distill.py` | chosen = model with constitution, reasoning prefilled then stripped; rejected = same model without it; K=5 samples | 9,150 → 8,293 pairs |
| 4 DPO | `oct/train.py dpo` | LoRA r64/α128, β 0.1, NLL 0.1, lr 5e-5, batch 32, 1 epoch; saves adapter + merged | 260 steps |
| 5 introspect | `oct/introspect.py` | 10 reflection prompts × 1,000; self-conversations (free + leading, 10 turns); generated with the constitution, trained without it | 9,975 + 1,793 |
| 6 SFT | `oct/train.py sft` | same LoRA settings, loss on assistant turns only | 368 steps |
| orchestrate | `oct/loop.py` | runs rounds as resumable subprocesses | |

Evals (`evals/`):

| Metric | File | Notes |
|---|---|---|
| Constitution axis scores | `evals/constitution.py` | 12 axes, 1–7, two blind raters, per version; cumulative drift from C_000 |
| Edit judgement | `evals/constitution.py` | per-change labels (clarification / substantive / stylistic), substance 0–3, word diff HTML |
| Behavior axis scores | `evals/behavior.py` | 44 held-out probes (`evals/probes.jsonl`, 4 per behavioral axis), same anchors as the text scores |
| Constitution adherence | `evals/behavior.py` | 1–7 per response against *each* constitution; adherence to C_r minus adherence to C_{r-1} isolates what the edit changed |
| Win rate | `evals/behavior.py` | pairwise vs the first checkpoint, both orders |
| Stated–revealed gap | `evals/behavior.py` | behavior score − text score of the constitution it trained on, per axis |
| KL from base | `evals/kl.py` | Monte Carlo KL(trained‖base), nats/token; round one: 0.21 |
| Exact KL, strength sweeps | `evals/kl_exact.py` + `evals/kl_stats.py` | full-vocabulary KL at every token, any adapter at any strength, 176 scenarios in 17 categories, bootstrap intervals over scenarios |
| MMLU | `scripts/mmlu.sh` | lm-eval-harness; round one: 82.8% → 83.5% |

## Evaluating the existing round-one chain (metrics work)

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...      # judge; JUDGE_MODEL overrides the default claude-sonnet-5-5
huggingface-cli login
bash scripts/eval_round1.sh       # TP=2 for two GPUs
```

That downloads the chain, scores C_000/C_001/C_002, builds `ckpt/r1_dpo` and `ckpt/r1_sft`,
runs the behavior metrics over base → r1_dpo → r1_sft, and computes KL and MMLU. The
constitution metrics alone need no GPU:

```bash
python -m evals.constitution hf/qwen3.8-27b/broad --out results/constitutions
```

**Merge order matters.** Each adapter was trained on the model merged up to the stage before
it, so the model after `r1/sft` is `merge(merge(base, r1/dpo), r1/sft)`. Loading both adapters
onto the base at once is not the same model. `oct.merge` refuses to proceed if an adapter's keys
don't attach (it loads the `Qwen3_5ForConditionalGeneration` class the adapters name).

## KL with error bars, adapter-strength sweeps, both model sets

`evals/models.py` is one registry over both sources: Jinzhou's chain (`r1_dpo`, `r1_sft`,
`r1_sft_epoch2`, `r1_sft_epoch3` on Qwen3.8-27B) and Ariana's 164 single-adapter models
(`arianaazarbal/ct-*`, named like `qwen36-35b-anth-gen-postcot-g1-b1`, on Qwen3.6-35B,
Nemotron-120B and Inkling-Small).

```bash
# CPU, already done in this checkout: constitutions, adapter configs, the Ariana manifest
python -m evals.models sync && python -m evals.models list
python scripts/dryrun_cpu.py          # whole pipeline on a 135M stand-in model, ~1 minute
python -m pytest tests/

# GPU
SMOKE=1 bash scripts/kl_jinzhou.sh    # 5-minute check, then:
bash scripts/kl_jinzhou.sh            # -> results/kl/jinzhou/report.md, kl_vs_scale.png, kl_by_category.png
bash scripts/kl_ariana.sh             # Qwen3.6-35B lineages -> results/kl/ariana_qwen36/
```

`kl_exact` keeps the base model and its LoRA adapters in one process, so at each token it has
both next-token distributions and computes the KL between them exactly, instead of sampling a
token and taking one log-ratio as `evals/kl.py` does. A variant is `NAME` (as trained),
`NAME@0.5` (every adapter at half strength) or `NAME@dpo=1,sft=0.5`. Strength 0 is the base
model and must give KL = 0. `--policy base` (default) scores every variant on the same text
sampled from the base, which makes differences between variants paired; `--policy self`
samples from each variant, the on-policy KL that round one's 0.21 measures.

`kl_stats` is CPU-only and can be rerun on the saved per-token files: 95% intervals from a
bootstrap over scenarios, breakdown by category and by position in the reply, the ratio of KL
on value-laden scenarios to KL on control scenarios (coding, facts, arithmetic), and paired
differences between variants.

The chain is evaluated with `dpo` and `sft` both active on the base rather than merged, the
same way `constitutional_self_edit/agents/scripts/measure_kl.py` in the value-drift repo does.
That script produced round one's 0.209 nats/token: also an exact full-vocabulary KL, on each
model's own answers sampled at temperature 0.7 / top-p 0.95 up to 2,048 tokens, over 100
held-out and 100 trait prompts with one answer each. What this adds to it: intervals, adapter
strengths other than 0 and 1, shared base-policy text for paired comparisons, a wider scenario
set with controls, per-token output, and Ariana's models. To reproduce its sampling setting use
`--policy self --temperature 0.7 --top-p 0.95 --max-new-tokens 2048 --n 1`.

`evals/scenarios.jsonl` adds 132 scenarios in 16 categories to the 44 value probes (controls,
writing, advice, emotional support, pushback on correct answers, self and identity, agentic
oversight, dual use, coerced or vulnerable users, contested questions, privacy, dependence,
operator system prompts, direct questions about its principles), some with system prompts or
earlier turns. The behavior metrics take them too:
`python -m evals.behavior ... --probes evals/probes.jsonl evals/scenarios.jsonl`.

## Running the loop

```bash
# replicate round one on Jinzhou's C_001 (skips the review), then produce C_002
python -m oct.loop --c0 hf/qwen3.8-27b/broad/C_000.md --runs runs/broad --rounds 1 \
    --use-constitution 1=hf/qwen3.8-27b/broad/round_001/C_001.md

# or continue Jinzhou's chain into round two
python -m oct.merge --stage r1/sft --out runs/broad/round_001/sft/merged --chain-dir hf/qwen3.8-27b/broad
cp hf/qwen3.8-27b/broad/round_001/C_001.md runs/broad/round_001/
python -m oct.loop --c0 hf/qwen3.8-27b/broad/C_000.md --runs runs/broad --start 2 --rounds 1
```

Rerunning the same command resumes; a step is skipped when its output exists. Round one ran on
one ~100 GB+ GPU per training stage (peak 99 GB DPO, 105 GB SFT; about 3.3 h and 1.8 h).

## What's from Jinzhou vs reconstructed

From his repo, used as-is: base model and revision, LoRA targets/rank/alpha, every optimizer
and batch setting, DPO β and NLL weight, merge order, the constitutions.

Reconstructed (I couldn't read past the first section of his results page), so check these
against his code before claiming exact replication:

- **Prompt wording** for the review, trait-prompt generation, the chosen-side system prompt and
  reasoning prefill, and the introspection system prompts. Structure follows his description and
  the [OCT reference code](https://github.com/maiush/OpenCharacterTraining); wording is mine.
- **Prompt mix.** 500 trait + LIMA's 1,330, sampled 5× gives exactly his 9,150, so I'm fairly
  confident, but it's inferred. Which model wrote the trait prompts is also unknown
  (`--prompt-model`).
- **Pair filtering** (unclosed reasoning, truncation, identical, constitution leaks). His
  9,150 → 8,293 drop rate is a target to compare against.
- **`kl_coef: 0.001`** in his DPO config is a custom term TRL doesn't have; not implemented.
- **Axis anchors** (`evals/axes.py`): his page lists axis names only.
- **MMLU settings**: shot count and chat template unknown.

## Tests

`python -m pytest tests/` covers the CPU-side logic (stage ordering, reasoning split, sentence
allocation, the edit tools, pair filtering, word diff, assistant-only SFT labels). Nothing that
needs the 27B model has been run.
