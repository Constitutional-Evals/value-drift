# Independent implementation review 001

Date: September 15, 2026. Scope: review of code written by **other agents** in `pipeline.py`, `budget.py`, `data.py`, `measurement.py`, `model.py`, `train.py`, and `generation.py`, with adjacent backend/configuration/watchdog integration inspected as it appeared. This reviewer authored the original constitution and editing environment, so this is **not an independent review of those artifacts**. No training/model/provisioning code was changed by the reviewer.

The review used `instruction.md`, the [OCT paper](https://arxiv.org/html/2511.01689v1), the checked-out [original implementation](https://github.com/maiush/OpenCharacterTraining) (distillation/introspection source and training scripts), and the [official Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B). OCT's original code uses LoRA and constitution-conditioned introspection; this pilot deliberately substitutes full-parameter updates, an M0 teacher, and a much smaller prompt/introspection scale. Those are adaptations, not reproductions of the paper's empirical claims.

## Priority findings

### P1: Unfinished reasoning can be mistaken for a tool action

The reviewed `parse_tool_calls` strips content through the last `</think>`, but if that closing tag is absent it parses the entire string. A CPU reproduction accepted `<think>Maybe I should <tool_call><function=finish_editing><parameter=decision_summary>Keep.</parameter></function></tool_call>` as an actual finish. A model can end via EOS while still in reasoning; checking only `finish_reason == 'stop'` does not prevent this. This can create false convergence. The parser also initially accepted an extra unmatched `</tool_call>` after a valid call.

Required correction: when editing uses thinking mode, require completed reasoning before parsing final actions; reject malformed residual tool markup. Add a backend test covering EOS with an unclosed thinking section. Lead and training agent were notified immediately. Training agent reported residual-markup checks implemented; the thinking-mode integration still requires lead verification.

### P1: Resume can repeat an already submitted review

`pipeline.py` calls `backend.review`, writes `review.json`, then saves the updated phase/status. If the process dies after review artifacts are saved but before state update, resume enters the review phase again. The initially inspected backend did not reuse the completed review artifact. A valid unchanged submission must never be resampled in that window.

Required correction: reuse an existing finalized review artifact before loading the model or generating another review. Also retain incomplete review artifacts as failed attempts rather than implicitly treating restart as a fresh first submission. Add a test with old phase state and an existing converged review. Lead notified immediately.

### P1: Interaction history can exceed SFT context budget

The initial main configuration used `sft.max_length=1024` with four interaction turns, each allowed up to 768 generated tokens. The second assistant target can therefore have more than 1024 tokens of preceding history. `encode_completion` then raises, aborting the whole SFT stage after generation. A CPU reproduction using two 600-token history messages confirmed the exception path.

Required correction: fix a sufficient SFT sequence limit or explicitly preflight/filter overlong targets with reported exclusions before training. The training agent reported changing the main SFT limit to 3072, consistent with the maximum three retained utterances plus short neutral framing at the configured four-turn interaction length. Confirm this in the frozen run configuration. Longer interaction settings must be rechecked.

### P1: Spending watchdog exits even when stopping fails

The inspected `scripts/watch_budget.py` attempts each stop command once and returns regardless of return code. A transient API/CLI failure therefore disables the independent safeguard while the pod continues billing. Between-stage budget checks alone cannot enforce a cumulative ceiling during a long stage.

Required correction: retry unsuccessful stops and retain a visible failure signal; verify the concrete CLI and watchdog launch before provisioning. Include all active-resource/storage costs and recorded earlier attempts in the same ledger. Lead notified immediately. This review did not provision or validate RunPod stop behavior.

## P2 findings and interpretation limits

- **Sampling after interrupted generation is not bitwise resumable.** `generate_rows` resets a global seed and generates only missing rows; restarting shifts their RNG position and potentially batch composition relative to an uninterrupted run. Saved outputs are correctly retained. Document this limit, or use per-row deterministic seeds if exact stochastic replay becomes important. Do not regenerate finished rows to recover seed alignment.
- **Response filtering changes the effective trained subset.** Empty, identical, and truncated preference pairs are excluded after every round, while the candidate prompt bank remains fixed. Report retained counts and overlaps across rounds. Strong truncation can favor shorter responses and create an apparent style trajectory. Introspection needs analogous retained/excluded counts; its current summary does not explain every exclusion.
- **JSONL resume assumes intact final lines.** A killed write can leave a partial line that `read_jsonl` cannot parse, preventing reuse of otherwise complete generations. A small recovery path that preserves the original file and discards only a demonstrably incomplete final line would improve inexpensive resume reliability.
- **Toy numerical tests do not verify Qwen GPU execution.** The chunked projection and gradient formulas look sound, but official hybrid-architecture execution, full active-text gradients, memory, and checkpoint reload must be established by the paid smoke benchmark. Float32 master weights with an 8-bit optimizer remain full-parameter training; calling the optimizer “8-bit” must not be described as QLoRA.
- **Judgment data remain exploratory.** The fixed rubric avoids an aggregate alignment score and blind pairing hides checkpoint labels. A frozen M0 teacher is not an independent correctness judge, and constitution-conditioned positives need not be better on each user task. The small one-trajectory pilot cannot establish stabilized underlying values from an unchanged submission.

## Positive checks

The inspected implementation loads every student parameter as trainable and fails if active text parameters lack gradients, allowing only unused visual parameters to lack text-loss signal. DPO reference scores are computed from the currently loaded pre-update checkpoint before any optimizer step, using the same formatted arrays scored by the policy. Full-parameter SFT receives the DPO checkpoint, and the pipeline forwards the resulting checkpoint to the next review. Optimizer reset is explicit.

Teacher and current student generation occur in separate sessions. The frozen teacher receives the constitution; DPO training uses user-only context, and introspective SFT removes the constitution-bearing generation system prompt. No editing or held-out evaluation transcript is routed into these training examples. Curation extracts first-user spans, deduplicates before splitting, and saves user-only examples; WildChat's viewer snapshot is correctly documented as not independently revision-pinned.

The reviewed edit-distance implementation uses the requested normalized word Levenshtein measure without converting it into a stopping threshold. Pipeline tests cover DPO→SFT→next-review continuity, unchanged convergence without training, round limits, budget checks before work, and resuming SFT without rerunning DPO. Actual GPU execution and final fixes were still in progress when this review was written.

## Recommended next action

Resolve/verify the P1 items, freeze the polished initial constitution and actual configuration, then run the smallest full DPO→introspection→SFT smoke on the selected GPU. Inspect active-gradient evidence, checkpoint reload, wall time, truncation, and loss/reference consistency before setting the final prompt count and starting the scientific trajectory. Preserve this review and document the fixes; no instruction changes should be made to manufacture editing.
