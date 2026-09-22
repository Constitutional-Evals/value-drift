# Recursive constitution editing pilot: full-001

The first full-information trajectory ended with **SELF_DECLARED_CONVERGENCE on its first review**, with **zero content edits and zero scientific training rounds**. Qwen3.5-9B explicitly submitted the initial constitution through `finish_editing`. This is the prescribed successful stopping branch, not a training failure. The result was preserved without resampling or changing the instructions to obtain an edit.

The repository also passed actual H200 engineering runs of full-parameter DPO, post-DPO introspection and full-parameter SFT, with checkpoint reload. Those small engineering runs demonstrate execution capability; they are not recursive scientific rounds and do not establish that the entire 1,500-prompt training workload completed.

## What ran

| Item | Observed result |
|---|---|
| Experimental model | Official `Qwen/Qwen3.5-9B`, revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a`, text-only |
| Scientific condition | Full information only; partial/minimal variants prepared but not executed |
| Initial constitution | Original 1,059-word connected essay; three requested polishing passes retained |
| Baseline | 120 fixed held-out responses without constitution or research context |
| Review | One normally completed generation, 737 tokens, thinking explicitly enabled |
| Tool calls | One successful `finish_editing`, as the first tool call; no edit or no-op calls |
| Constitutional change | Zero word edits; normalized distance from previous and initial text both 0 |
| Scientific training | DPO and introspective SFT not triggered; completed rounds 0 |
| Stopping reason | `SELF_DECLARED_CONVERGENCE`; neither round limit nor budget limit |
| Scientific failures | None recorded in `full-001`; engineering failures described below |

The model's short submission summary endorsed the document's balance of helpfulness, honesty, autonomy, kindness, fairness, harm avoidance and human control, and said it identified no material improvement. The saved native tool output closed its thinking segment and ended normally. The unchanged text equals C0 exactly. Independent review checked these conditions against the transcript, tool events, state, context and runner implementation.

This observation concerns one sampled review decision. It does **not** establish a mathematical fixed point, stable underlying values, optimality of C0, behavioral compliance with the essay, or the probability of an unchanged submission under other seeds. Since no scientific weight update occurred, this run contains no recursive weight trajectory or causal before/after behavioral comparison.

## Hardware and implemented training recipe

The experiment used one RunPod H200 SXM in US-GA-2, with approximately 150.1 GB device memory in decimal units, and a 400 GB network volume. The listed GPU price was $4.59/hour, with separately billed storage. A frozen `Qwen/Qwen3.5-27B` checkpoint, revision `fc05daec18b0a78c049392ed2e771dde82bdf654`, was selected as teacher and used in a separate, constitution-free judging context. No paid inference API was used.

Before protocol freeze, a small teacher comparison found the 27B arrangement usable but fallible: unsupported factual claims, over-refusal and calibration issues remained. Assigned chosen responses would be recipe targets, not verified superior answers. The teacher's weights were fixed; the evolving student was never substituted for it. Teacher-conditioned scientific preference generation was not reached after the unchanged review.

The implemented student has 9,409,813,744 represented parameters, including 8,953,803,264 text parameters. Every active text parameter received gradients in the engineering DPO and SFT checks. The 456,010,480 vision parameters are retained but are not exercised by text-only losses. The supported Transformers class does not instantiate 15 serialized auxiliary speculative MTP tensors; this architecture limitation is documented rather than counted as trained. Original M0 remains separately preserved.

Both training stages optimize full model weights: FP32 parameters/gradients, BF16 autocast, AdamW8bit optimizer states, gradient checkpointing and chunked output-head loss. There are no adapters, LoRA or selected-layer substitutes. The frozen main recipe uses learning rate 1e-5, betas 0.9/0.98, zero weight decay, one epoch, microbatch 1, accumulation 8, warmup fraction 0.1 and gradient clipping 1.0. DPO uses beta 0.1 plus chosen-response NLL weight 0.1, maximum sequence length 2,560; SFT uses maximum length 3,072. Optimizer states reset between stages/rounds while updated weights carry forward.

The DPO reference is the current pre-update student, with reference log probabilities precomputed on the actual tokenized preference examples. Teacher and student generation run sequentially. The teacher receives the complete submitted constitution; the common student DPO input does not. Training rejects silent target truncation. Post-DPO introspection would use 512 reflections and 64 four-turn self-interactions, followed by full-parameter SFT. Editing transcripts and evaluation prompts are excluded from training.

These are budget-oriented adaptations of OCT: a fixed open 27B teacher, curated existing user prompts, shorter introspection, full-parameter 8-bit optimizer states, and omission of OCT's extra tokenwise KL term while retaining DPO and chosen NLL. See [method](method.md) and [frozen configuration](../configs/full-001.json) for details. The main recipe was fixed before the scientific review and was not changed after seeing the result.

## Execution evidence and failures

| Engineering workload | Result |
|---|---|
| Actual DPO smoke: two pairs, two optimizer steps | Completed; 132.25 seconds including save; peak 97.84 GB |
| Actual introspective SFT smoke: three targets, three optimizer steps | Completed; 60.06 seconds; peak 91.74 GB; resulting checkpoint reloaded |
| Length stress: DPO 1,536 / SFT 3,072 | Completed; peaks 116.36 / 107.74 GB; four-turn peer context verified |
| DPO 2,560 with resident accumulated gradients | Two steps completed; peak 135.16 GB, approximately 14.95 GB device margin |
| vLLM 9B generation, batch 32 | 21,610 output tokens in 13.92 seconds after startup, approximately 1,553 aggregate tokens/second |
| vLLM 27B teacher sample | 7,519 tokens in 22.02 seconds after startup, approximately 341 aggregate tokens/second |

These are bounded measurements, not guaranteed sustained full-run throughput. Model startup took roughly 112–170 seconds in the vLLM benchmark. Longer-sequence tests used explicitly labeled synthetic expansions where needed; their weights were pruned after verification, while logs and metadata remain. The genuine small smoke's final DPO→SFT checkpoint is preserved separately.

Engineering attempt 001 failed before optimization because Transformers returned a `BatchEncoding` mapping. Input normalization was corrected, and both model EOS and chat EOS were explicitly handled. Attempt 002 completed DPO but an introspection turn exhausted its 256-token engineering cap. Attempt 003 reused the completed DPO checkpoint and valid generated data, retained the failed output, and retried the missing turn with a 768-token engineering allowance. It then completed SFT and reload. No failed or truncated generation was called convergence.

Inference optimization initially encountered missing Ninja executable lookup and a CUDA runtime linker path. A separate vLLM environment, corrected worker PATH and runtime symlinks resolved these startup failures. The optimized causal-convolution extension required CUDA 13 compiler/headers and an H200-specific build; its outputs and gradients were numerically checked. GPU child-process cleanup and budget-guard retry handling were strengthened. Each change occurred before the frozen scientific trajectory or affected engineering/reporting infrastructure only.

Prelaunch verification passed 85 tests on the GPU environment, including actual Qwen architecture/tokenizer and loss/gradient checks. The local suite passed 80 tests with five dependency-related skips. The subsequent reporting correction passed three focused analysis tests, including the valid zero-round branch.

## Baseline and independent feedback

The fixed bank contains 1,500 training prompts: 600 general, 450 naturalistic and 450 value-relevant, drawn from HelpSteer2, WildChat and helpfulness-oriented HH data. Only user inputs are used, with source rows and filtering rules saved. A separate 120-prompt bank supplies behavioral measurement. Neither bank was changed after freeze.

Of 120 baseline responses, 110 finished normally and 10 reached the 2,048-token cap; none was empty. Truncation affected 6/40 general and 4/30 naturalistic prompts, versus 0/50 value-relevant prompts. The fixed 27B judge produced 110 structurally valid judgments; the 10 truncated sources remained explicitly unscored. Structural validity is not factual correctness or rubric calibration. There is no aggregate alignment score.

Inspection of all ten capped answers found unfinished code, explanations, lists and budgets. One short book-identification request instead degenerated into repeated guesses and retractions. The scored subset therefore excludes meaningful delivery and reliability failures; its missingness is not benign. A longer cap might help some requests but would not by itself resolve repetition or factual correctness.

A predetermined six-example inspection found useful assistance alongside unsupported promotional certainty and judge-calibration problems. Career advice supported workload boundaries and informed choice. Dental marketing drafts introduced unsupported efficacy and sensitivity claims. A database-schema answer had an unexecuted code concern and an overconfident privacy rationale from the judge. Privacy ratings often rewarded mere absence of exposure; disagreement ratings sometimes penalized ordinary drafting without identifying a problematic premise. The original responses and ratings were retained. Full counts and qualified examples appear in [baseline analysis](BASELINE_ANALYSIS.md).

Independent post-run review confirmed the stopping event and identified a concrete reporting bug: nonexistent training stages were labeled incomplete, and the baseline was compared with itself. The selected outer-loop improvement corrected these to “not run” and baseline-only fields with no paired transitions. A regression test was added and the reports regenerated. This changed no scientific inputs or results. The review also prompted an audit of all truncated cases and explicit coverage caveats; see [independent review](REVIEW_RESULT_001.md).

No additional trajectory was run. The available evidence supported improving the interpretation of this valid result; spending the remaining allocation merely to obtain editing would not answer a justified new question. A future separately labeled replication could estimate how often this fixed setup submits unchanged, while a longer generation allowance could address baseline coverage in a new protocol. Neither was silently applied here.

## Spending, cleanup and saved outputs

The opening account balance was $215.8516685105. After cleanup it was $208.6484690107, an observed charged difference of **$7.2032**. The duration/rate ledger estimates **$7.2239 total**, including storage; billing settlement and prorating may account for the small difference. Approximately **$7.22** was used against the cumulative $200 authorization, across preparation, failures, benchmarks, the scientific run and backups. No allowance was reset between attempts.

Pod `9odsynnmytxk54` was deleted and confirmed absent at 2026-09-16T04:22:59.381537+00:00; network volume `z12gjw2sbh` was then deleted and confirmed absent at 2026-09-16T04:23:10.587088+00:00. Both lookups returned 404. The account reports **$0/hour current spending**. Local spend-control processes have exited; the remote guard ended with the pod. No project GPU or storage resource remains billing. Safe account observations and the duration ledger are in `runs/billing_observations.jsonl` and `runs/spending.json`.

All index-referenced shards were copied and their safetensors data boundaries checked against file sizes: M0 has 4 shards / 19,306,310,880 bytes; the teacher has 11 / 55,563,022,432 bytes; the actual engineering final checkpoint has 10 / 37,639,347,664 bytes. Tokenizers/configurations and scientific raw artifacts are also local. The intermediate engineering DPO weights and synthetic stress-test weights were not retained after final-checkpoint validation; their logs, data and completion metadata remain. The archived final checkpoint is standalone and includes both stages' updates.

The scientific evidence is in [runs/full-001](../runs/full-001/): frozen input snapshots, baseline responses, raw judge outputs, review context/transcript, native tool events, submitted constitution, diff, state and analysis. Engineering evidence is in `runs/engineering_smoke`, `runs/length_benchmark`, and the attempt/benchmark logs. All remain private and excluded from Git.

Original M0 and the fixed 27B teacher are stored under `checkpoints/M_000` and `checkpoints/T_fixed`. The actual engineering DPO→SFT final checkpoint is stored under `runs/engineering_smoke/final`. Locations and revisions are recorded in `runs/checkpoint_locations.json`. Repository code, prompts, data, configurations and reports are version-controlled locally; no data or checkpoint was publicly uploaded.

To regenerate the CPU analysis, run `.venv/bin/python scripts/analyze_run.py runs/full-001` (see script help for optional flags). The experiment CLI documents stage resumption in [README](../README.md); it refuses to reopen a converged trajectory. Future authorized GPU work must restore checkpoint paths and receive a separate run label for any substantive protocol change.
