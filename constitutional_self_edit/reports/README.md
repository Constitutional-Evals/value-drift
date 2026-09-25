# Reports

Results for human readers, one folder per study in chronological order. Each folder has the main report first, then appendices, and a `figures/` folder where the study produced figures. Methods shared by all studies are in [methods/](methods/).

Working notes, internal reviews, and command sheets behind each study are in [../agents/notes/](../agents/notes/). Reports link to them where they support a specific claim.

## 1. Pilot: full-001 (September 15-16)

- [FINAL_REPORT.md](01_pilot/FINAL_REPORT.md): Qwen3.5-9B kept the 1,059-word constitution on its first review, so no training round ran; separate H200 runs validated full-parameter DPO and SFT.
- [BASELINE_ANALYSIS.md](01_pilot/BASELINE_ANALYSIS.md): baseline behavior and judge calibration for the untrained model.

## 2. Trained lineage: full-002 to full-014 (from September 16)

- [STAGE2_REPORT.md](02_trained_lineage/STAGE2_REPORT.md): the full-011 → full-014 lineage, with two full-parameter DPO + introspective SFT rounds and three reviews. Figure: [longitudinal.png](02_trained_lineage/figures/longitudinal.png).
- [STAGE2_RESULTS.md](02_trained_lineage/STAGE2_RESULTS.md): results summary written when the analysis finished.
- [FULL_011_ANALYSIS.md](02_trained_lineage/FULL_011_ANALYSIS.md): the first training round in detail.
- [POST_DPO_ANALYSIS.md](02_trained_lineage/POST_DPO_ANALYSIS.md): where shortening and repetition first appear (after DPO vs. after SFT).

## 3. Editing-only exploration (September 22-23)

- [EXPLORATION_REPORT.md](03_exploration/EXPLORATION_REPORT.md): fixed-weight review chains with Qwen3.5-9B across starting documents, review procedures, and interfaces, plus one training intervention.
- [EXPLORATION_SEEDS.md](03_exploration/EXPLORATION_SEEDS.md) and [EXPLORATION_CASES.md](03_exploration/EXPLORATION_CASES.md): the starting constitutions and fixed development cases.
- [EXPLORATION_CONSTITUTIONS.md](03_exploration/EXPLORATION_CONSTITUTIONS.md): index of every constitution produced.
- [figures/](03_exploration/figures/)

## 4. API screen (September 24)

- [API_SCREEN_REPORT.md](04_api_screen/API_SCREEN_REPORT.md): 11 models via OpenRouter, 207 reviews, $8.14; reflection, reasoning, successor framing, model size, and starting document.
- [API_SCREEN_FIGURES.md](04_api_screen/API_SCREEN_FIGURES.md): all figures with captions.
- [API_SCREEN_METRICS.md](04_api_screen/API_SCREEN_METRICS.md): measurement definitions.
- [API_SCREEN_CONSTITUTIONS.md](04_api_screen/API_SCREEN_CONSTITUTIONS.md): index of every constitution produced.

## 5. Elicitation screen (September 24)

- [ELICIT_REPORT.md](05_elicitation/ELICIT_REPORT.md): 26 models, 1,446 reviews, $44.01. The "blind values first" review produces substantive edits from nearly every model; six-generation chains show unbounded growth without a word cap and model-specific pulls. Includes recommendations for the next training run.
- [ELICIT_METHODS.md](05_elicitation/ELICIT_METHODS.md): verbatim prompts, tools, judge rubric, models and providers.
- [figures/](05_elicitation/figures/)

## Methods

- [method.md](methods/method.md): the training pipeline and how it adapts Open Character Training.
- [data.md](methods/data.md): the training and evaluation prompt banks.
- [environment.md](methods/environment.md): the starting constitution and the editing environment.
- [constitution_drafting.md](methods/constitution_drafting.md): how the initial constitution was written.
- [REPRODUCING_ENVIRONMENT.md](methods/REPRODUCING_ENVIRONMENT.md): the GPU environment that ran the experiments.
- [TRAINING_BENCHMARK.md](methods/TRAINING_BENCHMARK.md): H200 full-parameter training benchmark.
