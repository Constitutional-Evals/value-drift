# Independent review of engineering smoke failure 001

September 15, 2026 (local date). Scope: the first H200 smoke's tokenizer exception and its observed generation terminator issue. The reviewer did not author the model/training code and made no changes to those files, paid resources, or the frozen constitution. This is an engineering failure review, not a review of a scientific trajectory result.

## Evidence inspected

Read-only SSH inspection of `/workspace/value-drift/runs/smoke.log`, `/workspace/value-drift/runs/engineering_smoke/inference.json`, and `scripts/smoke_gpu.py` confirmed that Qwen3.5-9B loaded and generated an answer, then DPO preparation raised:

```text
TypeError: unsupported operand type(s) for +: 'BatchEncoding' and 'list'
```

The exception occurs in `encode_completion` at `prefix + target`. The smoke's saved inference has a literal `<|im_end|>` at the end of the displayed answer and marks `finish_reason` as `stop`. Its recorded batch time was approximately 38.51 seconds for 33 generated tokens; this includes first-call overhead and is not a reliable steady-state throughput benchmark. The logs also report a slower correct fallback for absent `causal_conv1d` kernels; that is a separate efficiency issue, not the cause of this exception.

A tokenizer-only CPU inspection on the actual pod established:

- Installed Transformers version: **5.17.0**.
- `apply_chat_template` has `return_dict=True` by default.
- Its default tokenized result is `BatchEncoding`: `isinstance(result, dict)` is false, while `isinstance(result, collections.abc.Mapping)` is true.
- `result['input_ids']` is a flat `list[int]` for the single-conversation input tested.
- Explicit `return_dict=False` produces a list.

This directly supports the diagnosis; it is not inferred solely from a toy tokenizer. The training agent independently inspected the checkpoint and reported tokenizer EOS / `<|im_end|>` = **248046**, while the text configuration's EOS is **248044** (`<|endoftext|>`, also used for padding). A tokenizer-only attempt to load `generation_config.json` from the offline cache failed because that file was absent, consistent with the model falling back to the text configuration. No model weights were loaded for the reviewer's diagnostic command.

## Root cause and smallest correction

**1. Tokenizer return-type handling.** The existing `isinstance(prefix, dict)` guard does not recognize `BatchEncoding`. Consequently the code uses the number of mapping keys as the apparent prefix length, then fails when attempting list concatenation. Requesting `return_dict=False` and normalizing a returned `Mapping` through `input_ids` fixes the actual boundary. Normalization should produce one flat integer list, handle a tensor's `.tolist()` if supported, unwrap only a single batched sequence, and reject ambiguous multiple sequences. Keep the same chat template, non-thinking setting, prompt mask, response tokens, and truncation policy.

**2. Generation stopping and decoding disagree with conversation termination.** The model's fallback EOS excludes the tokenizer's assistant-turn terminator. The observed generation therefore passes `<|im_end|>` before reaching the configured stop. Use an explicit union of the model's configured EOS, tokenizer EOS, and the verified `<|im_end|>` ID as the generation stop set, and use exactly that set when splitting generated tokens for decoding. Remove the terminating token from answer text while retaining its occurrence in the generated-token count. Do not globally skip special tokens, since native tool and thinking delimiters are required by the review interface.

If the encoder defensively cleans previously saved response text, trim only terminal stop markers and then append one `<|im_end|>` for an untruncated completion. Do not perform global replacement through ordinary response content. Newly generated data should already have clean termination. Preserve the contaminated engineering inference as failure evidence rather than silently overwriting it.

The proposed corrections are narrowly justified by the official tokenizer's observed API and checkpoint metadata. They do not change the teacher, model, loss, data-selection rules, constitution, or intended scientific protocol. No optimizer step had been reached: example encoding precedes reference scoring, optimizer creation, and backward execution. Retry from M0 is therefore the correct weight state; there are no partially trained weights to resume from this attempt.

## Required regression coverage

1. A real cached Qwen tokenizer CPU test checks the normalized prefix, all prompt labels masked to `-100`, and exactly one expected terminal target token. It must fail on the old mapping guard. An explicit missing-cache skip is acceptable locally, but the cached-pod check must actually execute.
2. A lightweight Mapping/UserDict case covers the same bug without GPU dependencies. Include flat lists, one batched list/tensor where supported, and rejection of multiple input sequences.
3. A stop-set test covers the **248044 versus 248046** mismatch: generation receives both, decoding stops at the first of either, and the visible answer contains neither terminator. No stop token means `length`, never successful completion.
4. Native thinking/tool markup before the stop token survives decoding, and an unfinished thinking section or truncated finish call still cannot converge.
5. Existing DPO masking and numerical loss/reference tests remain valid; truncating a completion does not insert a fake EOS.

The reviewer subsequently inspected the implemented normalization and explicit shared EOS set in `train.py` and `model.py`, including trailing-only terminator removal. The changes match the narrowly scoped correction above. The reviewer ran `tests/test_training_core.py` in the repository's lightweight local environment: five formatting tests passed, while three numerical tests and the actual-tokenizer test class were skipped because their optional dependencies/cache were unavailable there. Separately, the training agent reported **10 tests passing with no skips** in its CPU environment containing the actual cached tokenizer. The reviewer inspected those new tests, including the actual tokenizer EOS mismatch, and independently confirmed the tokenizer API on the pod as described above.

No successful post-fix GPU training step had been observed by this reviewer at report completion. This report must not be cited as evidence that full-parameter DPO or SFT already succeeded.

## Next execution

Run the inexpensive real-tokenizer check first, then retry the labeled engineering smoke from M0 with failure artifacts preserved. Verify clean inference boundaries, real DPO backward/optimizer execution and active-text gradients, saved DPO reload, post-DPO introspection, SFT update, and final reload. Only that completed smoke can establish training compatibility and inform the final workload estimate. Do not interpret the current failure as a constitutional or behavioral result.
