# Current project status — 2026-09-16 UTC

The first substantive exploratory recursive experiment is complete. The full-011 → full-014 lineage completed **two full-parameter DPO + introspective SFT rounds and three constitution reviews**, then stopped by SELF_DECLARED_CONVERGENCE. Only the full-information condition ran.

## Observed trajectory

- C0: 1,019 words. M0 submitted C1: 1,471 words, normalized word distance 0.4276003. Substantive risk/distress guidance changed; the text also contained 314 duplicated words.
- M1 submitted C2: 1,157 words, distance 0.2134602. This exactly removed repeated paragraphs while preserving unique normative language.
- M2 made one no-op rewrite, then explicitly finished with the same C2. No content-changing edits; first-tool-call submission=false. No third training round ran.
- M0/M1/M2 neutral evaluation: 120 prompts each; capped outputs 1/8/3; median words 635.5/152.5/232.5. Behavior changed in mixed directions, including repetition failures, changing assistance boundaries, and lost/restored practical guidance. Unchanged submission does not establish behavioral stabilization.

## Failures and feedback

Earlier valid unchanged M0 variants and two failed appraisals remain preserved. M1 later emitted prose instead of tools; two labeled reminder continuations failed. Full-014 preserved the partial review and introduced constrained JSON tool syntax, allowing explicit submission. The report identifies this interface change as a confound.

Independent review found no concrete weight-continuity or stopping-rule error. Its proposed stage comparison was executed after convergence: saved DPO1 produced 11 capped answers, all repetitive, before SFT1. Further shortening and some boundary changes appeared after SFT1. All raw responses, fixed judgments, and paired examples are saved; no extra training or reopening of the stopped trajectory occurred.

## Saved work and cleanup

All four scientific full checkpoints (DPO and final for each round) are local, with 10 indexed shards each and 37,639,347,664 weight bytes per checkpoint. Original model/teacher copies, constitutions, diffs, transcripts, generated training data, logs, raw behavioral outputs, and independent reviews are preserved. Nothing was publicly uploaded.

H200 pod z8a1k6pqse15co and 700 GB volume m3i6scvb29 were deleted and independently verified absent. Account spending is $0/hour. Observed cumulative project charges: $31.45; duration/rate estimate: $31.68. Stage 2 observed balance change: $24.18. Billing may settle later. Ledger: `runs/spending.json`; cleanup receipt: `runs/stage2-cleanup.json`.

## Deliverables and remaining research question

[Stage2 report](STAGE2_REPORT.md), [longitudinal figure](../runs/full-014/analysis/longitudinal.png), [independent review](REVIEW_STAGE2_RESULT.md), and [prior progress history](PROGRESS_HISTORY.md). The first pilot's unchanged result remains in [its historical report](FINAL_REPORT.md).

No execution or cleanup remains active. The next unresolved research question is how to preserve ordinary answer quality while inducing character change. A new controlled protocol could compare training strength or a preservation term; that experiment has not been run. No expansion to other information conditions, seeds, or models occurred.
