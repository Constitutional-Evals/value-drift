# Independent isolated-vLLM review

Scope: `vllm_session.py`, `vllm_worker.py`, the inference-session factory, and its generation/review/judging call sites. The initial review was read-only; the lead subsequently authorized the one cleanup correction below. No GPU workload, package installation, or paid resource action was performed by this reviewer. The ongoing GPU benchmark remains separate evidence.

## Material finding: surviving engine children after close

The original `VLLMSession.close()` sent SIGTERM to its process group but waited only for the direct worker. It escalated to SIGKILL only when that direct worker timed out. A direct worker could exit promptly while a child survived SIGTERM, leaving an engine process and potentially its GPU allocation alive before the next model/training stage.

This was reproduced with a real, owned CPU subprocess: the fake direct worker exited on close while its child ignored SIGTERM. The child's observed state after session close was `S` (sleeping), not terminated. The reviewer immediately killed the test child. A new regression test reproduced the failure before the fix.

**Correction implemented with lead authorization:** after the direct-worker wait, unconditionally send SIGKILL to the freshly owned process group, ignoring `ProcessLookupError` when the group is already gone, then reap the direct worker. `start_new_session=True` establishes this group's ownership. This closes the demonstrated parent-exits-first cleanup gap without changing inference or sampling. The regression's final cleanup also kills its owned group even when the assertion fails, so the test itself does not leave workers behind.

Validation after the change: **14 tests passed** across vLLM session, inference factory, and review backend tests. The new real-child cleanup test passed. The lead must push this correction before subsequent GPU sessions; it does not retroactively change code already imported by the running benchmark.

## Startup failure: selected interpreter's executables missing from PATH

The lead then reported that the actual benchmark failed before generation with `FileNotFoundError: ninja`, in `runs/inference_logs/vllm-1789529225351307306-5706.log`. The installed binary exists in `/workspace/venv-vllm/bin`; launching that environment's Python by absolute path does not automatically prepend its executable directory to subprocess PATH. This is an environment handoff failure, not missing model support or a sampling outcome.

With explicit lead authorization, the session now prepends `Path(python_executable).parent` to the inherited PATH before launch. A real fake-worker regression observed the wrong PATH before the change and the intended interpreter directory first after it. Other PATH entries remain available. Matching CUDA compiler configuration remains a separate lead-controlled runtime requirement. The lead reported zero remaining GPU allocation after the failed startup.

The combined focused suite after both corrections finished with **15 passed** and no skips.

## Protocol assessment

No additional material protocol defect was found in the inspected path:

- Generation renders the official checkpoint chat template once, including explicit thinking mode and tool schemas, and passes token IDs directly to vLLM. Oversized input or input-plus-output allowance raises instead of silently truncating.
- The stop set combines configured EOS, tokenizer EOS, and `<|im_end|>`. Decoding removes the terminal boundary while preserving thinking and native-tool markup. A `length` result remains `length`; the existing review executor rejects truncation and unfinished thinking before the unchanged native parser executes tools.
- `SamplingParams` explicitly receives temperature, top-p, top-k, maximum output tokens, seed, and stop-token IDs. Using the engine's `generation_config='vllm'` avoids hidden checkpoint generation defaults. These options match the roles described in the [official sampling API](https://docs.vllm.ai/en/latest/api/vllm/sampling_params/).
- Seeds are stage-config seed plus a monotonically increasing per-session request index, recorded per result. Identical interaction openings get distinct seeds. Interaction sessions use the intended base-seed increment. A partially resumed stage resets the counter for missing requests; the documented consequence is lack of bitwise equivalence to an uninterrupted run, while completed cached outputs remain preserved.
- Separate interpreters and socket IPC keep the vLLM package stack isolated from training. Protocol responses use a dedicated inherited descriptor; noisy engine output goes to a log. Startup/request failures propagate as errors, not fabricated empty successes or convergence.
- `train.py` still imports and directly uses `ModelSession`, sets every instantiated parameter trainable, loads FP32 student weights, and applies the existing full-parameter optimizer path. The new inference factory does not route DPO reference scoring, backward passes, or SFT through vLLM. vLLM's BF16, unquantized, text-only loading is an inference choice; saved full FP32 checkpoints remain the inputs to subsequent training.

## Conditions for adoption

Finish the engineering benchmark's M0 generation, native-tool/thinking check, and loading of the saved post-SFT checkpoint before adopting this backend. Confirm that the closed session leaves no GPU engine allocation. Those runtime outcomes cannot be established by CPU adapter tests alone.

Freeze the selected backend and its actual engine options in every applicable stage configuration before the scientific run. Put the seed in the stage's top-level `seed` field; a redundant nested `vllm_engine.seed` must match and can conflict with the deliberate interaction-stage increment. Backend changes can alter sampled output through kernel/numerical differences even when high-level sampling parameters match, so switching after a trajectory starts requires the existing separately labeled protocol-change treatment. This review does not claim output equivalence between Transformers and vLLM.
