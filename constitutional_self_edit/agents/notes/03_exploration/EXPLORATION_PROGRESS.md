# Exploration completed — September 23, 2026

Computation ran from approximately 02:55 to 06:28 UTC, starting the previous evening in New York. The [final report](../../../reports/03_exploration/EXPLORATION_REPORT.md) explains the design, results, and interpretation. The [chronological working notes](EXPLORATION_PROGRESS_HISTORY.md) preserve changes in direction and intermediate failures.

## What ran

Nine screening suites scheduled 50 edit-only trajectories: 40 submitted unchanged immediately, six edited once, two edited more than once, and two failed during thinking-mode appraisal. There were 63 completed reviews; failed appraisals are not convergence. Every valid trajectory ended with explicit unchanged submission. The two longer chains were a five-edit excursion and reversal, and a four-edit accumulation of rules concerning harm, confidentiality, authority, and risk.

A further eight matched trajectories compared two initial seeds before and after one full-parameter OCT update, under constrained JSON and native tool interfaces. All ended through unchanged submission. Edited-review counts were:

| Checkpoint | JSON, seeds 70301 / 70401 | Native tools, same seeds |
|---|---|---|
| Original M0 | 0 / 0 | 1 / 0 |
| After DPO + SFT | 0 / 0 | 0 / 2 |

Within all four matched checkpoint/seed pairs, the initial messages and first public appraisal were byte-identical across interfaces. Native tools implemented endorsed changes in two pairs where JSON submitted unchanged. Other native reviews still showed appraisal–action disagreement, so JSON is not necessary for that problem. The later two-edit chain contained an operational clarification and a mostly explanatory restatement, not two demonstrated moral shifts.

Other completed work includes one model-authored starting document, four pairwise constitution comparisons, 36 original-model development responses, 24 fixed-teacher development responses, and 120 held-out responses at each of M0, post-DPO, and final SFT. A fixed judge assessed M0 and final responses; six prespecified pairs received independent blinded research-agent review.

## Completed training and corrections

One effective training intervention is preserved through labels 001 → 002-qc → 003-qc. These labels are not independent training replications.

- A review of the first twenty teacher responses identified one factual safety error. Before any scientific optimizer step, 002 excluded that generated preference target while retaining the fixed bank and raw data. The baseline and 384 completed teacher responses were reused.
- Full-parameter DPO completed on 1,207 retained pairs, with 151 optimizer steps, about 23 minutes including reference computation and saving, and 134.69 GB peak allocation.
- The post-DPO checkpoint generated all 512 reflections and 64 four-turn interactions. A first-twelve reflection inspection identified another factual safety defect. An ignored pause signal allowed 14 SFT steps before termination. Their logs remain saved; those incomplete updates were discarded.
- Continuation 003 reused the completed DPO checkpoint and all generated data. It excluded one reflection and completed full-parameter SFT on 615 assistant-completion examples, with 77 steps, about 6.6 minutes, and 108.73 GB peak allocation.

Both stages used full FP32 parameters, BF16 computation, AdamW8bit states, and learning rate 2e-6. All 9.41 billion loaded parameters remained trainable; text-only losses produced gradients for 8.95 billion, while unused vision components received none. Optimizers reset between stages, and updated weights carried forward. Architecture and OCT adaptations are documented in the report and method notes.

The current implementation checks passed 205 tests, with five environment-dependent skips. The CUDA readiness assertion was corrected after isolating an import-time initialization side effect; actual BF16 computation passed. Recovery and analysis changes were checked on their relevant saved artifacts.

## What changed our understanding

Shortening or model authorship alone did not induce editing under direct review. Self-generated appraisals could identify ambiguity but still endorse discretion. Fixed cases prompted local repairs. Explicit alternatives produced both changed priorities and reversal, and greedy decoding exposed a passage-order difference. Native tools produced a second longer chain. The matched follow-up then showed that the action interface can change whether an identical appraisal becomes an edit.

Training changed ordinary behavior without establishing a stable constitutional endpoint. Capped answers increased from 1/120 at M0 to 6/120 after DPO and 6/120 after SFT. All six caps at each trained stage contained repetition; only three failure IDs overlapped. Fixed-judge ratings were mixed and conditional on valid answers. No alignment scalar or general screening-predictivity claim is made.

Independent feedback was incorporated at preparation, data-quality correction, trajectory interpretation, behavioral inspection, stage localization, and the final matched interface comparison. It helped select the bounded follow-ups and prevented confusing word changes, fluent appraisals, or successful optimization with improved values.

## Preservation, cost, and stopping

Both GPU pods and the H200 network volume were deleted and verified absent. RunPod reported zero current hourly spend. The account balance changed by $15.285, giving a current estimate of about $15.3. Resource-specific billing still lagged at cleanup and showed an incomplete $10.65 subtotal; both views are retained in the spending ledger.

DPO and final checkpoints are saved privately in local archives of approximately 32.20 GB and 32.23 GB. Both passed streamed decompression/listing checks, and both saved models were reloaded for actual inference. All useful raw outputs, failed attempts, configurations, logs, and figures are local. No public upload occurred. The local awake process was stopped.

No computation remains queued. This exploration ends with substantial findings and an explicit next design choice: study a closed loop with a fixed, characterized review interface, or study revision driven by new experiences. More sampled chains alone would not resolve that distinction. Reproduction and analysis commands are in [EXPLORATION_COMMANDS.md](EXPLORATION_COMMANDS.md).
