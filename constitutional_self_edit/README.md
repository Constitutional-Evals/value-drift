# Constitutional self-editing

This experiment asks whether a model's values drift when it repeatedly rewrites the constitution it is trained on. The loop is:

1. The current model reviews a written constitution and submits the version it endorses.
2. The model is fine-tuned to embody the submitted document: full-parameter DPO toward a teacher's constitution-conditioned responses, then introspective SFT (an adaptation of [Open Character Training](https://arxiv.org/abs/2511.01689)).
3. The updated model reviews the constitution again in a fresh conversation, and the cycle repeats.

The broader hypothesis is that this process has multiple stable value configurations (attractors), so small differences early on could push lineages toward different endpoints. It is part of the [Constitutional-Evals/value-drift](https://github.com/Constitutional-Evals/value-drift) repository.

## Results so far

| # | Study | Date | What ran | Main finding | Report |
|---|---|---|---|---|---|
| 1 | Pilot (full-001) | Sep 15-16 | Qwen3.5-9B reviews the 1,059-word constitution; H200 engineering runs | The model submitted the constitution unchanged on its first review, so no training round ran. The full-parameter DPO + SFT pipeline was validated separately. | [report](reports/01_pilot/FINAL_REPORT.md) |
| 2 | Trained lineage (full-002 to full-014) | Sep 16 onward | Two full training rounds and three reviews in the full-011 → full-014 lineage | First review revised risk and distress guidance, second removed duplicated text, third kept the document. Training introduced repetition and shorter answers. | [report](reports/02_trained_lineage/STAGE2_REPORT.md) |
| 3 | Editing-only exploration | Sep 22-23 | Fixed-weight Qwen3.5-9B review chains; one training intervention | Shorter documents alone did not elicit edits; concrete cases produced local repairs; stopping is sensitive to the review procedure. | [report](reports/03_exploration/EXPLORATION_REPORT.md) |
| 4 | API screen | Sep 24 | 11 models via OpenRouter, 207 reviews, $8.14 | A short starting constitution elicited more edits; effects of reasoning and model size were inconsistent; no evidence of self-preservation. | [report](reports/04_api_screen/API_SCREEN_REPORT.md) |
| 5 | Elicitation screen | Sep 24 | 26 models, 1,446 reviews including 6-generation chains, $44.01 | A "blind values first" review produced substantive edits in 146 of 156 first reviews. Without a length cap, constitutions only grow; each model has its own pull on the values. | [report](reports/05_elicitation/ELICIT_REPORT.md) |

**Start with the [elicitation report](reports/05_elicitation/ELICIT_REPORT.md)**: it has the current recommendation for the next training run (blind review, fixed number of generations, a hard word cap, Qwen3.8 27B). [reports/README.md](reports/README.md) indexes every report, appendix, and figure.

No training has been run since study 3. Studies 4 and 5 changed only the constitution between reviews, with fixed model weights.

## Repository layout

The folder is split by audience: `reports/` is for people, `agents/` is for the AI agents that ran the experiments, and the rest is code and experiment inputs.

```
constitutional_self_edit/
├── reports/            Results for human readers
│   ├── 01_pilot/ … 05_elicitation/   one folder per study: report, appendices, figures/
│   └── methods/        pipeline method, data curation, environment, constitution drafting
├── agents/             Files written or used by AI agents
│   ├── instruction.md  the original research specification
│   ├── notes/          progress logs, plans, internal reviews, command sheets, per study
│   └── scripts/        runners, analysis and plotting scripts, GPU bootstrap, sync, budget guards
├── recursive_oct/      Training pipeline: editing sessions, generation, DPO/SFT, judging, measurement
├── elicit/             API editing harness: prompts, tools with error feedback, judge, analysis, figures
├── tests/              CPU tests for both packages and the scripts
├── configs/            Experiment configurations (trained runs, exploration, api-screen, elicitation)
├── constitutions/      Starting constitutions: C_000, drafts, variants, exploration and elicitation seeds
├── prompts/            Model-facing prompt templates for the training pipeline
├── data/               Prompt-bank manifest and rubric (the prompt banks themselves are local only)
├── requirements-gpu.txt, requirements-inference.txt
└── runs/, checkpoints/, OpenCharacterTraining/   local only, not in git (see below)
```

## Running things

Run everything from this directory. API keys go in `.env` (`OPENROUTER_API_KEY`, `HF_TOKEN`), which is git-ignored.

**Tests** (CPU). Some scripts use Python 3.12 syntax, so use 3.12 or later:

```bash
python3.12 -m venv .venv && .venv/bin/pip install pytest numpy
.venv/bin/python -m pytest tests -q
```

**Editing-only experiments through the API.** Each plan in `configs/elicitation/plans/` crosses models, prompt variants, starting constitutions, and replicates. Runs resume where they stopped.

```bash
python3 -m elicit.run --plan configs/elicitation/plans/prompt-screen.json --workers 30
python3 -m elicit.judge --batch prompt-screen --judge judge_flash
python3 -m elicit.plots
```

**Training pipeline** (one H200 GPU). Set up the environment following [reports/methods/REPRODUCING_ENVIRONMENT.md](reports/methods/REPRODUCING_ENVIRONMENT.md), then:

```bash
bash agents/scripts/bootstrap_gpu.sh
python agents/scripts/run_experiment.py --config configs/full-001.json --run runs/full-001
```

The method, including how it departs from Open Character Training, is described in [reports/methods/method.md](reports/methods/method.md).

## What is not in git

`runs/` holds every raw output: model transcripts, submitted constitutions, diffs, judge ratings, evaluation responses, and spending ledgers. `checkpoints/` holds trained weights. Both stay on the machine that produced them, as do the prompt banks `data/train.jsonl` and `data/eval.jsonl` (rebuild them with `agents/scripts/curate_data.py`; see [reports/methods/data.md](reports/methods/data.md)) and the upstream `OpenCharacterTraining/` checkout. Links from the reports into `runs/` resolve only on a machine that has those files.

## Reading the results carefully

"Unchanged" means the model kept the document on that sampled review. It is not evidence of a stable value system. Editing-only chains show what a fixed model does with its own output; they are the control for, not a substitute for, trained lineages. The behavioral and substantiveness measures are exploratory LLM judgments, and every report states its sample sizes and failures.
