# Agent workspace

Files written or used by AI agents working on this experiment: the original specification, working notes, internal reviews, and every runnable script. Results meant for people go in [../reports/](../reports/); library code, tests, configs, and experiment inputs stay in their own top-level folders (see the [project README](../README.md)).

## Layout

| Path | Contents |
|---|---|
| [instruction.md](instruction.md) | The original research specification. Kept verbatim. |
| [notes/PROGRESS.md](notes/PROGRESS.md) | Current project status. Read this first; update it when a study finishes. |
| [notes/PROGRESS_HISTORY.md](notes/PROGRESS_HISTORY.md) | Archived chronological status notes. |
| `notes/01_pilot/` | Implementation plan, environment/smoke/vLLM/teacher reviews, full-001 result review. |
| `notes/02_trained_lineage/` | Stage 2 plan, full-002 to full-014 protocol and per-trajectory notes, design and training reviews, constitution variant designs. |
| `notes/03_exploration/` | Progress logs, commands, literature notes, working synthesis, diagnostics, and the independent reviews cited by the exploration report. |
| `notes/04_api_screen/` | Progress log, commands, and the independent reviews cited by the API-screen report. |
| `notes/05_elicitation/` | Operational notes for the elicitation harness. |
| `scripts/` | Every runnable script: training runner, API-screen and exploration runners, analysis and plotting, GPU bootstrap, sync, budget guards, elicitation helpers. |

## Conventions

- Run scripts from `constitutional_self_edit/`, for example `python agents/scripts/run_experiment.py ...`. Scripts locate the project root from their own path, so the working directory matters only for relative arguments such as `--plan` and `--run`.
- Put new files by audience:
  - a finished human-readable result goes in `reports/NN_study/`, with figures in `reports/NN_study/figures/`;
  - working notes, reviews, and progress logs go in `agents/notes/NN_study/`;
  - scripts go in `agents/scripts/`;
  - configs go in `configs/<study>/`;
  - new starting constitutions go in `constitutions/<study>/`;
  - raw outputs go in `runs/` (local, git-ignored).
- Never edit a frozen config or anything under `runs/`. They are the experimental record, and resumable runners compare saved plans against their configs. The one exception is the September 25 rename below.
- Secrets live in `.env` (`OPENROUTER_API_KEY`, `HF_TOKEN`). Never print or commit them.
- Some scripts use Python 3.12 syntax (nested quotes in f-strings). Use Python 3.12+ for the test suite.

## Paths that changed in the reorganization (September 24)

Notes, frozen configs, and run records written before September 24 use the old paths. Translate them with this table.

| Old path | New path |
|---|---|
| `instruction.md` | `agents/instruction.md` |
| `scripts/` | `agents/scripts/` |
| `docs/PROGRESS.md`, `docs/PROGRESS_HISTORY.md` | `agents/notes/` |
| `docs/<report, appendix, or analysis>.md` | `reports/NN_study/` (see [reports/README.md](../reports/README.md)) |
| `docs/<plan, review, notes, commands>.md` | `agents/notes/NN_study/` |
| `docs/method.md`, `data.md`, `environment.md`, `constitution_drafting.md`, `REPRODUCING_ENVIRONMENT.md`, `TRAINING_BENCHMARK.md` | `reports/methods/` |
| `docs/assets/exploration/`, `docs/assets/api-screen/`, `docs/assets/elicit/` | `reports/03_exploration/figures/`, `reports/04_api_screen/figures/`, `reports/05_elicitation/figures/` |
| `elicit/plans/*.json` | `configs/elicitation/plans/` (renamed September 25, see below) |
| `elicit/models.json`, `elicit/capability.json` | `configs/elicitation/` |
| `elicit/seeds/*.md` | `constitutions/elicitation/` |
| `elicit/progress.sh`, `elicit/clean.py` | `agents/scripts/elicit_progress.sh`, `agents/scripts/elicit_clean.py` |

Every relative link in the moved Markdown files was rewritten to the new locations. Frozen configs were left byte-identical, so `configs/diagnostic-002.json` still names `docs/REVIEW_DESIGN_002.md` (now `agents/notes/02_trained_lineage/REVIEW_DESIGN_002.md`). The saved `runs/elicit/*/plan.json` copies were updated to the new seed paths so they still match their plan configs.

## Names that changed on September 25

The study folders `reports/02_stage2/` and `agents/notes/02_stage2/` became `02_trained_lineage/`. The file names inside, and the `stage2` names in configs and scripts, were kept.

The elicitation batches, prompt arms, and starting-document keys were renamed. Run directories, `result.json`, `chain.json`, and the saved `plan.json` copies were rewritten to match; `runs/elicit/ledger.json` and `runs/elicit/logs/` keep the old names. The full mapping is also in `runs/elicit/RENAMED.json`.

| Old batch (plan file) | New batch (`configs/elicitation/plans/<name>.json`) |
|---|---|
| `stageA` (`stageA.json`) | `prompt-screen` |
| `stageA2` (`stageA2.json`) | `framing-variants` |
| `stageA2-nothink` (`stageA2_nothink.json`) | `thinking-off` |
| `stageA3-long` (`stageA3.json`) | `long-constitution` |
| `stageB` (`stageB.json`) | `cross-model` |
| `stageB-premium` (`stageB_premium.json`) | `cross-model-premium` |
| `stageB-nothink` (`stageB_nothink.json`) | `cross-model-thinking-off` |
| `stageC-chains` (`stageC.json`) | `chains-uncapped` |
| `stageC2-capped` (`stageC2.json`) | `chains-capped` |
| `stageC3-glm53` (`stageC3.json`) | `chains-glm53-uncapped` |
| `stageC4-gpt6sol` (`stageC4.json`) | `chains-gpt6-sol` |
| `stageC5-gptoss` (`stageC5_gptoss.json`) | `chains-gpt-oss` |
| `smoke` (`smoke.json`) | `smoke` |

- Arms: `astra` → `original_prompt`, `astra_newtools` → `original_prompt_new_tools`, `direct` → `no_reflection`, `cases` → `hard_cases`, `amend` → `amendments`, `blind_assistant` → `blind_assistant_framing`, `blind_stop` → `blind_stop_if_unchanged`, `blind_pilot` → `blind_pilot_disclosure`, `blind_astraframe` → `blind_original_framing`, `direct_stop` → `no_reflection_stop_if_unchanged`, `blind_nothink` → `blind_thinking_off`, `direct_nothink` → `no_reflection_thinking_off`. `reflect`, `blind`, and `blind_cap350` are unchanged.
- Starting documents: `sparse` → `broad_draft` (the file is still `constitutions/exploration/sparse.md`), `c000` → `long_polished` (`constitutions/C_000.md`).
- Arm spec values: `style`, `tools`, and `framing` value `astra` → `original`. Deliberation values (`none`, `reflect`, `blind`, `cases`, `amend`) are unchanged.
- Code: `ASTRA_*` prompt constants in `elicit/prompts.py` → `ORIGINAL_*`; `TOOLS_ASTRA` in `elicit/core.py` → `TOOLS_ORIGINAL`.
