# Pre-main implementation audit

Scope: current Transformers path in pipeline, training, generation, budget handling, and rendered review context against `instruction.md`. The reviewer did not author these training/pipeline components. The unfinished vLLM backend is explicitly excluded. The main trajectory had not begun. No implementation or paid job was changed by this review.

## 1. Resolve training-time truncation before freezing the recipe

**Material issue found:** rejecting length-limited generations does not prevent cutting completed responses later during training. `encode_completion` slices the target to `max_length - prefix_length`. Under the provisional DPO limit of 1024, a completed response generated within the 768-token output allowance can therefore lose its ending. This changes the actual preference example and, in an extreme case, can turn answers that differ only near the end into identical training targets. Counting truncations only after training completes is too late to decide whether this is acceptable.

An actual cached-Qwen tokenizer CPU audit of all **1500** fixed training prompts found formatted user-only prefix lengths:

| Minimum | Median | 95th percentile | Maximum | Prefixes above 255 tokens |
| ---: | ---: | ---: | ---: | ---: |
| 19 | 41 | 286 | 580 | 95 (6.3%) |

These 95 prompts **can** truncate near-cap responses at length 1024; this is a risk bound, not a claim that 95 actual generated pairs have already been truncated. A DPO limit of **1536** covers the observed maximum prefix plus the generation allowance (580 + 768 = 1348), subject to checking the actual encoded examples. The maximum situated-reflection prefix was **604**, comfortably within SFT's 3072 limit plus a 768-token response. The four-turn interaction dataset retains at most three generated utterances per supervised history, also consistent with 3072 at the present allowance and short framing.

**Correction observed during review:** the lead added `audit_training_lengths`, which writes `sequence_lengths.json` and rejects any truncated target by default before reference scoring or optimizer updates, for both DPO and SFT. Explicit `allow_target_truncation=True` is required to opt out. This resolves the silent-training aspect. The provisional `full-001.json` still showed DPO 1024 when inspected; set the final validated limit before changing `frozen` to true. The training agent confirmed that the realistic engineering benchmark now targets DPO 1536. Any explicit truncation opt-out must be part of the frozen scientific recipe, not an unrecorded response to a later failure.

## 2. Freeze file contents, not only their path strings

`pipeline.py` compares the resumed config dictionary with `config.json`, but the config stores paths to the prompt banks, introspection templates, recipe text, and constitution. `ExperimentBackend` rereads these files, with recipe text reread for each review and introspection templates reread for each round. Shared prompt templates are also read when rendering a review. Editing a referenced file leaves the config equality check satisfied and can silently change the scientific protocol after a restart or between rounds. A changed bank with reused IDs can also mix old cached generations with new ones.

**Action before main:** save ordinary run-specific copies of the selected training/evaluation banks, introspection bank, recipe, and model-facing review templates; use those copies for the trajectory and resume. Alternatively compare their saved text with the current files and refuse changes. No hashing system or elaborate provenance infrastructure is needed. Keep C0 and the generated constitution sequence separate from these fixed materials. Preserve the exact rendered instructions already recorded for each review. This matters particularly because the outer development loop may continue editing shared repository files while completed scientific artifacts must remain interpretable.

## Verification relevant to readiness

No additional material defect was found in current-reference selection, full-parameter continuity, the explicit-finish stopping rule, or the inspected cumulative spending calculation. The completed smoke's SFT artifact confirms three optimizer steps starting from its DPO checkpoint, 9,409,813,744 trainable parameters, 8,953,803,264 parameters receiving gradients, only visual parameters inactive, zero truncated sequences, and nonzero changes in all five representative sampled parameter groups. These facts establish the short smoke path, not the memory or throughput of the longer main workload.

The current pipeline reuses finalized review artifacts after a state-write interruption, treats incomplete recorded reviews as editing failures, and does not reopen convergence or round-limit results. Twelve focused pipeline/backend/budget tests passed during this review. Budget estimates include the current pod and network volume under one cumulative $200 ceiling with a $15 reserve; the watchdog now retries until stopped status is confirmed. Continue running that independent watchdog because between-stage checks do not interrupt long generations or training stages. Actual shutdown/cleanup accounting and final configuration freezing remain lead responsibilities.

The model-facing recipe matches the inspected teacher/student/reference/SFT arrangement. It accurately distinguishes assigned teacher preferences from quality judgments and describes continuing weights and fresh conversations. No editing transcript or held-out response enters the inspected training inputs. Recheck these boundaries for the separately implemented inference backend before using it; this audit does not cover it.

After the truncation guard landed, the combined local pipeline/backend/budget/training-core check finished with **18 passed, 5 optional dependency/cache skips**, including the new default-reject/explicit-opt-out length-audit test.
