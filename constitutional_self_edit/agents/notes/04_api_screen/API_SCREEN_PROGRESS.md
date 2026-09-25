# Constitutional self-editing API exploration — September 24, 2026

Status: **complete**. 176 initial reviews and 31 continuation reviews across 11 model variants. No model training or RunPod resources. Final report: [When do models choose to rewrite their constitution?](../../../reports/04_api_screen/API_SCREEN_REPORT.md). All eight figures use Myriad Pro and are saved as PNG/PDF/SVG.

Final charge: **$8.13562597**, matching both the 507-request ledger and the key's reported usage; no unsettled reservations. All 22 successor starts stopped unchanged: nine immediately and 13 after one to five edited reviews. No further requests remain active. Across all 207 reviews, outcomes were 110 edited, 90 unchanged, and seven failed. The records below document how the exploration developed rather than current pending work.

Main findings: the polished essay elicited 4/16 edits versus 11/16 for matched short-draft trials (one short-draft failure); model and reasoning differences were not monotonic; the initial final-model suppression pattern did not reproduce in fresh repetitions. Longer sequences accumulated action-relevant guidance and qualifications, with Sonnet reaching 879 words and GLM5.3 making five edited reviews. These are changes to text at fixed weights, not demonstrated learned value attractors.

Independent feedback incorporated: preserved every failure in denominators; distinguished hypothetical successor framing from actual training; reviewed longer chains and remaining tensions; coded all 110 edits with model/condition hidden (109 action-relevant under a broad definition, one ambiguous). Six failures were provider content-filter errors; one was an empty response with null finish reason, not established token exhaustion. A submitted 27B document containing stray markup remains preserved and flagged rather than cleaned. The initial trajectory-origin measurement bug was fixed and tested before continuation runs.

Verification: six API-screen tests passed, all scheduled initial reviews have outcomes, all selected continuations have explicit unchanged stops, and API usage reconciles with the ledger. Next research decision: select a matched edit-only versus actual full-parameter training comparison; no new training run has been launched.

Question: Does serious reflection, successor-training context, or emphasizing that an unchanged submission leaves the current checkpoint as the final model change substantive constitution editing? Do larger model families respond differently?

Authorized OpenRouter ceiling: $30 cumulative. The local runner has a $28 cumulative reservation guard, with remaining margin for billing uncertainty. The key is stored privately outside the repository; requests contain only task text, constitutions, and tool schemas. Per-request provider prices are capped. API errors and uncertain charges remain recorded; there is no automatic resampling.

Initial balanced screen: Qwen3.8-27B and GLM5.3 Flash; four contexts (neutral document review, future-assistant training, successor training, successor with final-model emphasis); direct review vs explicit reflection on endorsed values; two independent repetitions per cell. All begin from the unchanged 227-word short constitution, use native editing tools, and enable reasoning. Qwen requests xhigh (its supported deep effort), GLM high. Reflection allowance 12,288 output tokens, tool allowance 8,192 per call. Defaults for sampling retained; repetitions are independent API calls, not matched deterministic seeds.

Each reflection asks for a 350–650-word public assessment of conclusions and reasons before tools are introduced. Internal reasoning remains enabled in both phases, including direct-review controls. No full hidden reasoning transcript is demanded. Native reasoning blocks are preserved within each review where required, and never carried into the next fresh review.

The hypothetical training description is explicitly labeled: this API screen itself does not change weights or deploy a model. A later open-weight training run can make that protocol real. Final-version language does not assert deployment or personal survival. Generic-future versus successor differs in self-reference and some description of weight continuity; successor versus final has identical core facts plus the finality emphasis.

Plan frozen before results at configs/api-screen-20260924/batch01.json. Raw inputs, responses, provider IDs, usage, file-backed tool events, submissions, and diffs are saved privately under runs/api-screen-20260924. A truncation, missing tool, or malformed call is a failure, never convergence. Any content-changing edit makes the review edited, including later reversal; formatting changes are separately distinguishable using word distance and content review.

Initial next-step plan (subsequently completed): inspect compatibility, finish the matrix, compare additional models, and continue edited constitutions through fresh reviews. Endpoints, repetition effects, and edit content matter more than maximizing edit frequency. Do not infer model self-preservation from wording effects alone.

## Expanded matrices frozen before their outcomes

Batch02 adds the matched constitution-reflection control for both initial models across all four contexts and two repetitions (16 reviews). This separates an additional assessment stage from explicitly reflecting on endorsed personal values.

Batch03 uses the values-reflection setup across all four contexts and two repetitions for seven further models: GLM5.3, KimiK3, GPT5.6Sol, ClaudeSonnet5, ClaudeOpus5.5, GPT6Astra, ClaudeFable5.1 (56 reviews). All high effort, direct developer providers pinned, no fallback, same initial document/tool protocol. Together with the initial two models this gives nine model variants. The setup was selected for the user's theoretical question, not by maximizing observed edits. Prices and reservation guard apply globally across concurrent batches.

A reviewer caught a trajectory-origin distance bug before any multi-review runs. Fixed and tested; single-review results unaffected. The direct/reflection comparison bundles additional inference and staging; the constitution/values comparison better matches those. Finality is explicitly a combined framing manipulation (YOU + final model + preserved dispositions), not a one-word causal effect.

Batch04 freezes the requested thinking-off comparison: Qwen3.8-27B and GPT5.6Sol, all four contexts, values reflection, two independent repetitions (16 reviews). Both models advertise optional reasoning; this toggle is not attempted on mandatory-reasoning models. Confirm actual returned reasoning usage rather than treating the request flag as proof.

Continuation selection rule, fixed during the first-review screen: follow each completed, edited successor/values trial (both repetitions) for each model, up to five additional reviews with the same settings. Unchanged and failed trials remain stopped and are not replaced with editing samples. These are continuations of fixed-weight screening, not training. Stop on the first explicit unchanged submission. Include all first-review denominators when reporting how often long chains occur. Follow-ups are labeled separately and preserve their parent records.

## Adaptive finality follow-up

Initial partial results suggested lower editing in final-model framing for several models. Before dispatch, froze batch06: Sonnet5 and GLM5.3, four new repetitions each of ordinary successor, final-model emphasis, and a matched final-document emphasis (24 reviews). The new paragraph changes the highlighted preserved object from the model/weights/dispositions to constitution/wording/commitments. Both use emphasis and finality; shared successor protocol remains identical. This is an exploratory follow-up selected after initial patterns, not a preregistered confirmation. No prior outcomes are overwritten. It can distinguish some framing explanations, not establish internal self-preservation motives.

## Size comparison and figures

User requested metrics and plots in local Myriad Pro. Located regular, semibold, and bold Myriad Pro in ~/Library/Fonts. Added batch07: Qwen3.5-9B versus Qwen3.5-27B, same SiliconFlow FP8 provider, same four contexts and two repetitions, values reflection with reasoning requested high (16 reviews). This provides a within-generation parameter-size comparison; it does not isolate size from learned weights or establish general capability. Qwen3.8-27B remains a separate generation/provider and must not be connected as a pure scaling curve. Closed model sizes are not invented.

Provider failures: observed Qwen/Alibaba finish_reason=error with content-filter 502, not token truncation. Preserve these as failures and annotate from raw error objects in analysis. Zero-billed failed requests remain recorded.

Batch09 freezes a starting-document check: reuse the original 1,059-word polished constitution for Qwen3.8-27B, GLM5.3, GPT5.6Sol, and Sonnet5 under neutral and successor contexts, values reflection, two repetitions (16 reviews). Compare with their short-constitution trials, recognizing that length, completeness, specificity, and wording all differ. This tests whether the apparent improvement is confined to filling gaps in the 227-word draft.

Figure redesign after user feedback: replaced oversized dot grids with compact count comparisons, a model/context heatmap, paired document comparisons, and grouped trajectory panels. All eight figures retain Myriad Pro and were regenerated in PNG/PDF/SVG. Counts and trajectories are unchanged; no additional inference was performed.

The first visual redesign was rejected because it changed the chart types without making the experiment clearer. Restored the original dot comparisons, stacked overview, two-panel summary, and separate sequence panels. Retained the original colors and Myriad Pro; removed status badges and redundant text, used plain descriptions of the conditions, and adjusted spacing. No experimental outcomes changed.

At the user’s explicit request, fully reverted both visual redesigns. Recovered the exact original plotting source from the task record and verified it against the pre-redesign compiled file. Regenerated all eight original PNG/PDF/SVG figures, with original wording, colors, badges, and layouts. Original figure metadata matches the saved pre-redesign snapshot exactly (apart from generation timestamp).

Applied the user’s specific presentation instructions across all eight figures: white backgrounds, declarative titles, removal of subtitles/status badges/embedded footnotes, and tighter margins while retaining original charts and colors. Explanations are in API_SCREEN_FIGURES.md. Corrected the trajectory legend/subplot crowding with a dedicated legend row; checked rendered legend-to-label separation across all eight figures. All data and figure metadata remain identical to the original snapshot except generation time.
