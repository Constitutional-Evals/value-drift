# Stage 2 exploratory results — living status

**One actual full-parameter DPO+SFT round is complete. Its M1 checkpoint has been evaluated on all 120 held-out prompts. The second constitution has now been explicitly submitted in full-014, and round-2 preference generation is running. There is no completed M2 checkpoint or M2 evaluation yet.** This describes the locally synchronized [full-014 state](../runs/full-014/state.json); it makes no completion or cost estimate for unfinished work.

## Launches and continuation lineage

| Run labels | Observed outcome | New completed training rounds |
|---|---|---:|
| full-001, full-002 | Original 1,059-word constitution submitted unchanged; full-002 used case audit | 0 |
| full-003, full-004 | Appraisal variants exhausted output allowances without submission; editing failure, not convergence | 0 |
| full-005–full-008 | Foundational constitution variants submitted unchanged | 0 |
| full-009, full-010 | Practical 1,019-word constitution submitted unchanged; full-010 used a direct editing request | 0 |
| full-011 | Thinking-disabled first review edited C0→C1; DPO, introspection, SFT, and M1 evaluation completed; second review then failed to call a tool | **1** |
| full-012 | Continued the existing M1 review with a bounded reminder; model removed duplicates but did not submit | 0; inherited round 1 |
| full-013 | Continued that same partial review with one additional reminder; still no submission | 0; inherited round 1 |
| full-014 | Continued with constrained JSON tool syntax; explicit submission of C2; round-2 preference generation active | 0 additional so far; inherited round 1 |

The first ten labels are separate exploratory M0 launches, including the original full-001 result. Full-011 begins the trained lineage; full-012–014 are separately labeled interface continuations of that lineage, not independent trained replications. Saved generations and partial edits were replayed rather than erased or resampled. The interface changes remain real experimental interventions and limit any claim of an uninterrupted fixed review protocol. See [branch provenance](../runs/full-014/branch.json) and the [living report](STAGE2_REPORT.md).

## Observed changes

C0→C1: **1,019→1,471 words**, normalized consecutive word distance **0.4276003**. Risky-choice and distress guidance changed, the ordinary reversible-action initiative default was removed, and three paragraphs were duplicated. C1 contains 314 extra repeated words; edit distance is not a measure of normative change.

C1→C2: **1,471→1,157 words**, distance **0.2134602**. Direct comparison confirms removal only of extra copies of the same three paragraphs, apart from terminal newline formatting. The risk-boundary tension and other substantive C1 guidance remain. The successful full-014 submission finalized the model's already-recorded deduplication; it did not introduce another substantive policy revision. Because C2 differs from C1, the ordinary edited-submission path starts the next OCT round.

Round 1 retained **1,210/1,500 preference pairs** (286 truncated, four identical pairs excluded). DPO ran 152 optimizer steps; SFT ran 76 steps on 605 assistant-target sequences. Both completion reports record zero target truncations. Introspection retained 481/512 reflections and 62/64 conversations; the fixed small content check found a mixture of requested reflection and ordinary task answering.

M0→M1 raw responses show **119→112 normal endings**, **1→8 truncated outputs**, and median length **635.5→152.5 words**. All eight M1 truncated outputs display repetition/degeneration. Fixed examples include a newly imposed dental-marketing refusal, lost workload-boundary advice, and substantial compression. The fixed judge scored 119 M0 and 112 M1 answers; truncated sources remain unscored. Its helpfulness ratings decreased on 52 matched complete answers, increased on one, and were unchanged on 59. These are separate observations, not an overall alignment score or a causal attribution to a constitution paragraph. Full details and caveats are in [the first-update analysis](FULL_011_ANALYSIS.md).

The selected launches cannot estimate unconditional edit frequency or isolate thinking-mode effects. No stable constitutional or behavioral endpoint has yet been established. Baselines reused across launches are the same saved M0 sample, not independent replications; full-001's earlier lower-cap baseline is distinct.
