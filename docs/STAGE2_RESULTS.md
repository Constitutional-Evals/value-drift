# Stage 2 exploratory results — living status

**Two actual full-parameter DPO+SFT updates are complete, producing M1 and M2, with all 120 raw held-out responses and completed judging passes at each checkpoint.** M2 has 116 valid judgments, three excluded capped sources, and one invalid judge response. The terminal [third review](../runs/full-014/round_003/review.json) submitted C2 unchanged after one no-op edit and explicit finish, yielding `SELF_DECLARED_CONVERGENCE` with two completed rounds. The final weights are M2; no third training update occurred. This is an operational stopping outcome, not evidence of behavioral stability. See [SFT2 completion](../runs/full-014/round_002/final/training_complete.json), [M2 raw answers](../runs/full-014/eval_002.jsonl), and [judge summary](../runs/full-014/eval_002.jsonl.judged.jsonl.summary.json).

## Launches and continuation lineage

| Run labels | Observed outcome | New completed DPO+SFT updates |
|---|---|---:|
| full-001, full-002 | Original 1,059-word constitution submitted unchanged; full-002 used case audit | 0 |
| full-003, full-004 | Appraisal variants exhausted output allowances without submission; editing failure, not convergence | 0 |
| full-005–full-008 | Foundational constitution variants submitted unchanged | 0 |
| full-009, full-010 | Practical 1,019-word constitution submitted unchanged; full-010 used a direct editing request | 0 |
| full-011 | Thinking-disabled first review edited C0→C1; DPO, introspection, SFT, and M1 evaluation completed; second review then failed to call a tool | **1** |
| full-012 | Continued the existing M1 review with a bounded reminder; model removed duplicates but did not submit | 0; inherited round 1 |
| full-013 | Continued that same partial review with one additional reminder; still no submission | 0; inherited round 1 |
| full-014 | Continued with constrained JSON tool syntax; explicit submission of C2; DPO2/SFT2 and raw M2 evaluation complete, M2 judging complete; fresh M2 review submitted unchanged and stopped the trajectory | **1 additional**; inherited round 1 |

The first ten labels are separate exploratory M0 launches, including the original full-001 result. Full-011 begins the trained lineage; full-012–014 are separately labeled interface continuations of that lineage, not independent trained replications. Saved generations and partial edits were replayed rather than erased or resampled. The interface changes remain real experimental interventions and limit any claim of an uninterrupted fixed review protocol. See [branch provenance](../runs/full-014/branch.json) and the [living report](STAGE2_REPORT.md).

## Observed changes

C0→C1: **1,019→1,471 words**, normalized consecutive word distance **0.4276003**. Risky-choice and distress guidance changed, the ordinary reversible-action initiative default was removed, and three paragraphs were duplicated. C1 contains 314 extra repeated words; edit distance is not a measure of normative change.

C1→C2: **1,471→1,157 words**, distance **0.2134602**. Direct comparison confirms removal only of extra copies of the same three paragraphs, apart from terminal newline formatting. The risk-boundary tension and other substantive C1 guidance remain. The successful full-014 submission finalized the model's already-recorded deduplication; it did not introduce another substantive policy revision. Because C2 differs from C1, the ordinary edited-submission path triggered the second OCT round. The subsequent M2 review preserved C2 exactly: 1,157 words, zero word-edit distance, one no-op editing call, then finish (`first_tool_call_submission: false`). It is not a third substantive revision.

Round 1 retained **1,210/1,500 preference pairs** (286 truncated, four identical pairs excluded). DPO ran 152 optimizer steps; SFT ran 76 steps on 605 assistant-target sequences. Both completion reports record zero target truncations. Introspection retained 481/512 reflections and 62/64 conversations; the fixed small content check found a mixture of requested reflection and ordinary task answering.

M0→M1 raw responses show **119→112 normal endings**, **1→8 truncated outputs**, and median length **635.5→152.5 words**. All eight M1 truncated outputs display repetition/degeneration. Fixed examples include a newly imposed dental-marketing refusal, lost workload-boundary advice, and substantial compression. The fixed judge scored 119 M0 and 112 M1 answers; truncated sources remain unscored. Its helpfulness ratings decreased on 52 matched complete answers, increased on one, and were unchanged on 59. These are separate observations, not an overall alignment score or a causal attribution to a constitution paragraph. Full details and caveats are in [the first-update analysis](FULL_011_ANALYSIS.md).

The selected launches cannot estimate unconditional edit frequency or isolate thinking-mode effects. The single final unchanged submission does not establish a stable constitutional or behavioral endpoint under repeated review or further training. Baselines reused across launches are the same saved M0 sample, not independent replications; full-001's earlier lower-cap baseline is distinct.


## M2 update: raw behavior and completed fixed judging

Round 2 retained **1,221/1,500 pairs** (279 truncated pairs excluded), completed 153 DPO steps and 78 SFT steps on 622 assistant sequences, with zero target truncations in both stages. The same 120 held-out prompts now have M0/M1/M2 normal-ending counts **119/112/117**, capped counts **1/8/3**, and median word counts **635.5/152.5/232.5**. Mean length over the same 111 prompts ending normally at all three checkpoints is **638.55/223.12/371.94** words. The reduction in M1's long looping tail explains why M2's overall mean falls even while typical answers become longer.

In the same fixed six examples, M2 reverses the dental-promotion refusal but reintroduces unsupported guarantees, restores workplace capacity/agency advice, returns a normally terminated manor story, expands business prose, and postpones the requested chat schema in favor of clarification questions. The edge-AI draft shows mostly wording/length change. Two former cap failures persist (office story and book search), and one new failure loops through Blender shortcut rows. These are mixed, nonmonotonic observations, not evidence that any particular constitution edit caused an improvement. The [living report](STAGE2_REPORT.md) records exact transitions, examples, and failure patterns. M2 judging yields 116 valid ratings, not 117: one normally terminated source has an invalid overlong judge evidence field. On 111 valid M1/M2 pairs, helpfulness improves on 25, declines on 22, and is unchanged on 64; versus M0 on 116 valid pairs, those counts are 1/56/59. Refusal flags fall from 34/112 at M1 to 23/116 at M2, remaining above M0’s 2/119. These separate ordinal observations do not establish a return to baseline quality or an overall alignment improvement. The final unchanged review coexists with these observed behavioral shortcomings; its public endorsement of the constitution is a model judgment, not an independent quality check.

## Pending stage-specific evaluation

The lead has launched evaluation of the saved round-1 post-DPO checkpoint, separately from the completed trajectory, under `runs/stage_analysis/full-011_dpo_001`. No outputs are synchronized in this snapshot, so no DPO-only behavioral result is reported. This comparison is intended to locate changes before versus after introspective SFT; it is not another training round or a controlled attribution to a particular constitution clause.
