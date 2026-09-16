# Full-014: constrained tool syntax

After one completed full-parameter OCT round, the model's fresh review proposed edits in prose. A bounded reminder elicited a real deduplication edit, but two subsequent responses continued repeating the plan without submission. Full-011, full-012 and full-013 preserve these failures and the partial edit. None is convergence, and the unsubmitted edit has not been trained on.

Full-014 changes the review output format to one JSON object containing `name` and `arguments`. A vLLM JSON schema permits exactly the existing edit_constitution or finish_editing function, with their existing argument schemas. It constrains syntax, not the chosen function or document contents. The model can submit unchanged in a fresh review. No minimum edit count, constitutional content requirement, or researcher-written revision is added.

The current interrupted review is continued by replaying its four saved generations, including the actual edit. The exhausted final prose response remains in history. A format-transition message is added only before the first new constrained request, at seed30405. Earlier responses are not resampled or retroactively presented as having received the new format instruction. Future rounds begin fresh with the JSON guide and seed30401. Native structured tool-call history and ordinary file-backed effects are retained.

The vLLM implementation uses StructuredOutputsParams(json=schema) through SamplingParams(structured_outputs=...). Installed API source and official v0.29 documentation were checked. Non-vLLM inference rejects this option explicitly. JSON-mode review requires thinking disabled, as already configured in this trajectory. Truncation, invalid arguments, nonunique passage replacement, and missing finish remain failures. The same no-op, edit/revert, and self-declared convergence rules apply.

This interface change is scientifically consequential and separately labeled. It does not establish that the earlier and later review protocols are interchangeable. Weights, teacher, prompt bank, DPO/SFT settings, evaluation and sampling values remain fixed. The branch inherits M1 and the original first training round; the administrative maximum remains five completed rounds in total. Parent checkpoint paths remain explicit in branch.json.

Focused tests covered schema choices, transport, parsing, native replay, format transition, unchanged submission, real edits, no-ops and reverts. Integration checks passed before the actual GPU continuation was launched; no extra diagnostic model reviews were run.
