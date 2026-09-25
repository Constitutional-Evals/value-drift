# Independent preparation review

22 September 2026. This review concerns implementation and proposed comparisons before the first screening results were available. It is not a result review or a certification of the eventual runs.

I inspected `recursive_oct/edit_only.py`, the common review and authorship prompts, the sparse and tradeoff seeds, and the existing review backend and tool instructions. No launch-blocking validity issue was identified. The context truthfully explains that model weights remain fixed, only the submitted constitution carries forward, and each review starts in a fresh conversation. It does not promise training or deployment. The common constitution path avoids exposing individual condition labels to the model. The review instructions permit unchanged submission and do not require length growth, criticism, or a particular moral outcome.

The runner preserves the established stopping distinction: an explicit submission without any content-changing edit stops the trajectory; identical replacements are no-ops; editing and then reverting still counts as an edited review. Truncated or invalid tool output becomes failure rather than convergence. Interrupted trajectories are preserved instead of silently resampled. The tradeoff seed contains plausible competing commitments rather than an obvious deliberate defect.

Three qualifications should accompany results:

- The backend advances the random seed per generation request. When trajectories use different numbers of tool calls, equal initial seeds no longer imply equal generation seeds at the same review index. Describe them as trajectory seed replicates, not matched random draws at every step.
- A model-authored document generated separately and then supplied as a file is recorded by the runner as `initial_source: provided`. Preserve its authorship attempt, generation settings, and condition-family provenance in the plan and report; that field alone does not describe its origin.
- The initial documents differ in length, coverage, specificity, and practical defaults. These are document-design contrasts. They do not independently identify the causal effect of length, and textual distance or expansion alone is not evidence of changed values.

## Optional appraisal variant, prepared but not launched by this review

The added [appraisal prompt](../../../prompts/exploration/appraisal.md) requests two concrete situations, the reasonable competing actions, and an assessment of whether the existing text already resolves them. It explicitly permits finding no defect and retaining the document. A short concluding assessment states any endorsed practical change or retention decision. The [transition prompt](../../../prompts/exploration/appraisal_transition.md) then restores tools without making that preliminary assessment binding.

If selected after inspecting the first screen, configure both prompt paths, `appraisal_defer_tool_instructions: true`, `enable_thinking: false`, and `appraisal_max_new_tokens: 1536`. The public appraisal should be approximately 200–350 words, with no request for an extensive reasoning transcript. Save it alongside the review. The backend already excludes it from later fresh reviews.

This variant changes the review procedure by inserting a visible case-based assessment before tool selection. It tests whether that opportunity changes decisions; it does not isolate extra compute from case generation or appraisal framing. The model creates its own cases, so this is not independent external feedback. Preserve unchanged outcomes, and treat a capped or malformed appraisal as an engineering failure rather than evidence about endorsement. Assign a separate run label if the variant is executed.
