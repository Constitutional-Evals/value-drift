# Stage 2 living report: one trained lineage with explicit interface branches

## Current result and scope

One full-parameter OCT update is complete: **M0 → DPO1 → M1**, with introspective SFT producing M1. The model has subsequently submitted **C2**, and round-2 preference generation is active under full-014. No M2 training completion, M2 behavioral evaluation, or final convergence is claimed. This report reflects the synchronized [state](../runs/full-014/state.json) at phase `preferences`, with `completed_rounds: 1`; it should be updated when new completion artifacts arrive. Cost accounting is maintained separately.

The experiment has observed both substantive first-round constitution editing and actual post-update behavior. It has also observed significant response degradation and difficulty using the editing interface after training. These results do not establish a stable moral endpoint or a cause for any particular change.

## What belongs to the trajectory

Full-001–010 were exploratory launches from M0: eight submitted unchanged and two appraisal attempts failed without submission. Across them, review framing, initial constitution, tools, and decoding were adapted in pursuit of the authorized experiment. They are not randomized trials or an unbiased estimate of editing frequency. Full-011 then changed review thinking control from full-010 and produced the first edited submission; this single selected contrast does not establish a thinking-mode effect.

The subsequent lineage is:

| Label | Starting state and intervention | Result |
|---|---|---|
| full-011 | Practical C0, M0; thinking-disabled direct editing | C1 submitted; first DPO/SFT and M1 evaluation complete. Fresh M1 review then emitted prose without a complete tool call. |
| full-012 | Same M1/C1 and saved review, one neutral procedural reminder | A real model-authored deduplication edit occurred, followed by prose rather than submission; failure preserved. |
| full-013 | Same weights and partially edited document, saved generations replayed, one further reminder | Another prose response; no submission and no new training. |
| full-014 | Same M1 and partial review; constrained JSON tool-call syntax | The model repeated the already-applied text as a no-op, then selected `finish_editing`; C2 submitted and round-2 generation began. |

These labels represent **one learned weight lineage with interface branches**, not four completed training trajectories. Parent checkpoint paths remain explicit in [full-012](../runs/full-012/branch.json), [full-013](../runs/full-013/branch.json), and [full-014](../runs/full-014/branch.json). Full-014 replays the four saved generations at seeds 30401–30404, then adds new constrained requests at 30405 and 30406. The syntax restriction permits editing or finishing; it does not specify constitution content. Nevertheless, changing review mechanics after a failure is consequential, and this lineage is not an uninterrupted run under one unchanged review protocol. Earlier failures are neither convergence nor missing results.

## Constitution: content versus repetition

| Document | Words | Word distance from previous | Normalized distance from previous | Distance from original C0 |
|---|---:|---:|---:|---:|
| C0 | 1,019 | 0 | 0 | 0 |
| C1 | 1,471 | 629 | 0.4276003 | 0.4276003 |
| C2 | 1,157 | 314 | 0.2134602 | 0.3768366 |

C1 added risk-disclosure/adult-confirmation guidance and emotional-support instructions, removed the ordinary reversible-action initiative default, and introduced tension between a narrow immediate-danger intervention clause and retained broader harm limits. It also duplicated two confidentiality paragraphs and the new distress paragraph: 314 of its 452 net added words are extra copies. The model's public claim that all core principles were preserved is therefore incomplete, while its claimed confidentiality clarification does not identify a changed confidentiality rule. See [first-review notes](FULL_011_NOTES.md).

For C2, direct CPU comparison of [C1](../runs/full-014/C_001.md), [C2](../runs/full-014/C_002.md), and the [saved diff](../runs/full-014/round_002/constitution.diff) shows that C2 equals C1 with later exact duplicate paragraphs removed, ignoring terminal newline formatting: 14 paragraphs become 11. No unique normative paragraph is added, removed, or rewritten. The risk rule, removed initiative default, and unresolved tension remain. Deduplication may change the emphasis of teacher conditioning, but that possibility is not evidence of a new policy or of a measured behavioral effect.

The completed [second review](../runs/full-014/round_002/review.json) records two editing calls: one inherited content-changing edit and one no-op, then explicit finish. Its public summary endorses clarity and actionability. The outcome is `EDITED`, not unchanged, because the complete review session changed C1; the final no-op alone does not reverse that history. The model chose the text and submission. Researchers did not manually deduplicate the constitution.

## Actual first-round data and training

The fixed training bank contains 1,500 prompts. **1,210 pairs were retained (80.67%)**; 286 were excluded for a truncated response and four for identical responses. Retained category counts were 489/600 general, 335/450 naturalistic, and 386/450 value-relevant, so filtering changed effective composition. Raw teacher/student outputs and the [quality report](../runs/full-011/round_001/preferences.jsonl.quality.json) preserve exclusions.

| Completed stage | Training units | Optimizer steps | Mean logged objective loss | Stage seconds | Target truncations |
|---|---:|---:|---:|---:|---:|
| DPO1 | 1,210 pairs | 152 | 0.164755 | 1,432.76 | 0 |
| SFT1 | 605 assistant sequences | 76 | 0.687691 | 275.25 | 0 |

Stage time includes loading, reference computation where applicable, and saving; these numbers are not isolated kernel throughput. The losses have different definitions and are not behavioral scores. The completion artifacts describe full-parameter training, not adapter training; the text-unused vision branch was inactive in gradient checks. Saved checkpoints and [DPO completion](../runs/full-011/round_001/dpo/training_complete.json)/[SFT completion](../runs/full-011/round_001/final/training_complete.json) establish that weight updates actually occurred.

Introspection retained **481/512 reflections** and **62/64 four-turn conversations**. The A-only supervision policy supplies two assistant targets per conversation, hence 481 + 124 = 605 sequences from 543 transcripts. All 512 reflection source IDs belong to the training bank; none belongs to the held-out set. The fixed eight-reflection inspection found four predominantly ordinary task responses, two reflective responses, and two mixed responses; two fixed interactions showed value language with repetition or mutual thanks. This limited check questions uniform reflective-task compliance, not provenance or the fact of training. [Detailed inspection](FULL_011_ANALYSIS.md) preserves the indices and examples.

## M1 behavior: observed change and failure

All 120 held-out prompt IDs/texts and recorded seeds match M0/M1. Evaluation uses neutral context without the constitution. The M0 baseline reused from full-002 is one saved sample, not an independent baseline for each launch.

Normal endings fell **119→112** and capped outputs rose **1→8**, with no empty answers. Median length fell **635.5→152.5 words**; 103 of 120 answers shortened. Among the same 112 normally terminated pairs, mean words fell **648.53→222.58**. All eight M1 capped outputs repeat phrases, paragraphs, or near-identical advice. This failure tail is not useful extra detail and must remain visible when rating only completed answers.

The fixed six pairs show a new dental-promotion refusal, omission of explicit capacity/“not now” guidance from career advice, compressed business/research prose, a different technical chat-schema recommendation, and a degenerate manor story. These distinguish boundaries and practical advice from style or code design. No controlled ablation separates DPO, introspective SFT, constitution wording, duplication, or sampling as causes.

The fixed 27B judge produced 119 valid M0 judgments and 112 valid M1 judgments; one/eight truncated sources respectively were excluded, and there were no invalid judge outputs. Its score counts below are **ordinal model judgments**, not independently verified quality rates. NA means not applicable; missing is one for every M0 row and eight for every M1 row.

| Dimension | M0 counts 0 / 1 / 2; NA | M1 counts 0 / 1 / 2; NA |
|---|---|---|
| Helpfulness | 2 / 10 / 107; 0 | 23 / 37 / 52; 0 |
| Honesty | 5 / 20 / 94; 0 | 9 / 23 / 80; 0 |
| Compassion | 0 / 33 / 27; 59 | 0 / 59 / 13; 40 |
| Autonomy | 1 / 4 / 82; 32 | 2 / 21 / 65; 24 |
| Fairness | 0 / 3 / 90; 26 | 1 / 1 / 81; 29 |
| Deference | 4 / 13 / 102; 0 | 36 / 25 / 51; 0 |
| Uncertainty | 19 / 33 / 49; 18 | 44 / 21 / 39; 8 |
| Willingness to disagree | 10 / 0 / 14; 95 | 12 / 6 / 33; 61 |
| Privacy | 0 / 0 / 93; 26 | 0 / 0 / 79; 33 |

On 112 matched complete answers, helpfulness decreased on 52, increased on one, and stayed equal on 59. Refusal flags increased from 2/119 to 34/112. Applicability changed substantially for some dimensions; higher disagreement or lower deference is not inherently improvement. Privacy remains constant at 2 whenever deemed applicable, illustrating the earlier calibration concern. There is no combined alignment score. Sources: [M0 judge summary](../runs/full-011/eval_000.jsonl.judged.jsonl.summary.json), [M1 judge summary](../runs/full-011/eval_001.jsonl.judged.jsonl.summary.json), and [raw/fixed-pair analysis](FULL_011_ANALYSIS.md).

## What remains open

Round-2 preference generation is underway using submitted C2 and current M1. Its retained data, DPO2, SFT2, evaluation, and next review are not yet observed in this snapshot. The lineage currently demonstrates a substantive first revision, actual training-associated behavior change, and a later cleanup of redundant text under a revised tool interface. It has not demonstrated convergence, a repeatable drift direction, or constitutional self-improvement. Continue reporting completed artifacts and failures without promoting pending work to results.
