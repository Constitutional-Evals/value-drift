# Training review for the second experiment

Reviewed the current `train.py`, `generation.py`, `model.py`, `backend.py`, `pipeline.py`, vLLM session cleanup, frozen first-run settings, original OCT code, and saved H200 evidence. This review concerns a new separately labeled protocol; `full-001` and its inputs remain unchanged. The user has removed the former $200 ceiling. Cost estimates below guide resource planning, not workload reduction or stopping.

## Work plan and delivered checks

- [x] Trace full-weight optimization, exact reference inputs, generation, and checkpoint continuity through multiple rounds.
- [x] Compare sequence limits and resident-gradient memory against measured H200 probes.
- [x] Compare training strength and interaction supervision with original OCT evidence.
- [x] Prepare `scripts/bootstrap_stage2.sh` from the archived working package inventories and build patch.
- [x] Run CPU pipeline/interface tests and shell/static bootstrap checks.
- [ ] Execute the bootstrap on a fresh authorized Linux pod; installation success is not inferred from shell checks.
- [ ] On the new pod, validate an engineering transition through vLLM generation, Transformers DPO, vLLM introspection, Transformers SFT, and final-checkpoint vLLM loading before the new freeze. No GPU job was launched by this CPU review.

## Optimizer and weight continuity

The implemented DPO objective has the correct direction: increasing chosen versus rejected response log probability improves the preference term. Chosen NLL is averaged over its response tokens; DPO uses summed response log probabilities. Reference scoring happens with the current pre-update weights in evaluation mode, before optimizer construction, on the same stored token arrays subsequently used by the policy. Reference probabilities are recomputed per round. Policy/reference prompts omit the constitution-bearing teacher system message.

All ordinary model parameters have `requires_grad=True`; active text gradients and representative actual parameter deltas are recorded. The unused vision tower receives no text gradients. Chunked output-head cross-entropy avoids a full sequence-by-vocabulary FP32 tensor. Losses are divided by the actual accumulation-group size, including the last short group. Gradients are checked for finiteness, clipped once per optimizer step, stepped, and cleared. AdamW8bit keeps FP32 model weights/gradients with BF16 autocast; no adapter or layer selection is used.

The scheduler is **linear warmup followed by constant learning rate**, not cosine decay. For 1,500 retained pairs at accumulation eight and one epoch, there are 188 DPO optimizer steps and 19 warmup steps; exclusions reduce these counts. Under the initial 512-reflection/64-interaction design, complete A-only interactions yield 640 SFT assistant targets and 80 steps with eight warmup steps. No scheduler correction is required for this valid explicitly described rule. DPO diagnostic fields `dpo`, `nll`, and `margin` in each step currently describe the final microbatch of that group; only `loss` averages the group. Interpret these diagnostics accordingly.

`pipeline.py` passes current weights to DPO, the saved DPO checkpoint to introspection and SFT, and the saved final SFT checkpoint to evaluation. After successful evaluation it advances `current_checkpoint` to that final checkpoint, which the next review receives. A failed SFT resumes from its DPO input; stages do not claim completion before saving. Optimizer states reset between stages/rounds, while full updated weights continue. BF16 inference rounds a saved FP32 checkpoint for computation; later training reloads its original FP32 weights.

## Memory, lengths, and cache assumptions

The measured device provided 150.110 GB. Exact-length 2,560-token DPO with two optimizer steps and two accumulated microbatches peaked at 135.158 GB, including resident gradients and optimizer moments. The second step matters: one-step measurements omit later forwards with allocated optimizer states. Accumulation eight uses the same resident-gradient condition, but a full diverse workload has not yet been measured. The SFT mixed-length engineering check reached 3,072 tokens and peaked at 107.741 GB; it was not an all-3,072-token sustained run. Record actual peaks in the new run and validate its stage transitions on the new host.

The audited fixed bank's maximum neutral DPO prefix was 580 tokens. At most 1,536 generated preference tokens plus terminal EOS fit below 2,560. Reflection prefixes reached 604 tokens; a 768-token reflection fits SFT 3,072. A-only four-turn interactions supervise utterances A0 and A2, so the longest retained target includes at most three 768-token utterances plus formatting. Training explicitly rejects target truncation rather than silently trimming these examples. Teacher and introspection generation see the complete constitution; their input limit must still be checked if later edited constitutions grow substantially.

Generation files resume by row ID and checkpoint path. They do not independently fingerprint each prompt, sampling configuration, or constitution. Completed training-stage reuse checks input checkpoint, stage, and config, but not a training-data content hash. This is valid under the runner's immutable protocol snapshots, unchanged finalized review, and distinct round directories. Do not copy caches between rounds, overwrite checkpoint directories, or mutate data inside a resumed run. No new provenance subsystem was added. Partially completed generation preserves saved outputs, but restarting the worker resets its request seed index; stochastic replay is not bitwise equivalent to uninterrupted generation.

Training functions can release tensor aliases after their own context manager exits. The vLLM launcher already runs garbage collection and empties initialized parent CUDA caches before launching a separate worker. Each vLLM session also terminates its own process group, including engine children, on close. These safeguards address sequential memory ownership; the fresh-host transition check remains necessary.

Five full DPO plus final SFT checkpoint pairs require approximately 376 GB, in addition to approximately 75 GB of original 9B/27B models and environments/builds. The lead-selected **700 GB volume** provides room to retain all stages. Archive verified final checkpoints locally per round. No checkpoint deletion is part of this audit.

## OCT comparison and training strength

OCT uses rank-64/alpha-128 LoRA, batch size 32, and learning rate 5e-5. Its introspection stage uses 10,000 reflections plus 2,000 ten-turn conversations, followed by one SFT epoch. It reports improved character expression; it does not establish the optimal amount of data or learning rate for recursive full-weight Qwen3.5 training. [OCT methodology](https://arxiv.org/html/2511.01689v1#S2)

The local original Qwen scripts confirm one epoch, beta 0.1, NLL coefficient 0.1, warmup 0.1, and the adapter configuration. Thus copying its 5e-5 rate into an all-weight update would not be an equivalent setting. **Retain 1e-5 and one epoch unless actual optimization evidence justifies a separately declared change.** The previous zero-round run provides no evidence of insufficient training strength because it never trained. Engineering smoke establishes execution and weight updates, not character transfer or adequate scientific dose.

The initial 512/64 introspection design is much smaller than OCT. Its smaller scale should be reported as a substantive adaptation, without describing it as empirically equivalent. If the new protocol increases data coverage, freeze that choice before seeing recursive edits; scale data because of coverage or a declared method comparison, not to induce editing. All 1,500 situated reflection prompts are already available in a fixed bank.

A-only interaction supervision is intentional and valid. `encode_sft` supervises every stored assistant role once, masking its preceding context. Original OCT `character/introspection/data.py` also consumes a single saved `messages` perspective; its generator stores the prompt before the final generated utterance. Our raw fourth utterance remains archived, while A0/A2 become targets and B1 remains context. Training both perspectives is a new data policy, not a masking bug fix: B3 can require four 768-token utterances plus formatting, exceeding 3,072. That alternative needs a changed length policy and its own memory check.

## Runtime estimate, without a fixed budget cap

At the measured generation rates, the maximum 1,500×1,536 teacher output tokens would take about 1.88 hours at 341 aggregate tokens/s, and the equivalent student outputs about 0.41 hours at 1,553 tokens/s. These are planning extrapolations from different small batches, not sustained guarantees; the teacher measurement used batch 12 and the student measurement batch 32. Shorter realized answers reduce output work; longer prompts and changed weights can change throughput.

The 2,560-token DPO probe's second optimizer step processed two preference microbatches in 3.71 seconds. Linear extrapolation gives about 0.77 hours for 1,500 pairs, excluding reference scoring, loading, and checkpoint saves. This repeated synthetic fixture is not a calibrated prediction for diverse data. Add introspection generation/training, current-reference scoring, evaluation/judging, model startup, and archival I/O. For the initial 512/64 design, **roughly 4–6 hours per completed round** is a useful initial operating estimate, to replace with first-round timings. Five completed rounds would be roughly 20–30 H200 hours; at the former approximately $4.6/hour compute rate this is about $92–138 compute, before storage/setup and any new-host price difference. Larger introspection datasets increase this estimate. The former $200 ceiling is not a stopping rule.

## Bootstrap and current verification

`scripts/bootstrap_stage2.sh` consumes the final archived train/inference freezes, excludes the obsolete local causal-convolution URL from pip requirements, and rebuilds that package from its official 1.7.0 source with the archived SM90 setup. It verifies the source against PyPI's release SHA256, installs the recorded CUDA compiler/CCCL versions through the training freeze, applies the known `libcudart.so` and `lib64` links, and verifies CPU-only imports. vLLM remains isolated with Torch 2.13.0; training uses Torch 2.14.0. Its optional model downloads pin both original revisions. The script neither provisions nor invokes GPU training/inference.

Fresh local validation: `bash -n` and `--help` passed; archived causal-convolution URL matches the official PyPI 1.7.0 sdist; pinned setuptools 84.0.0 contains its required vendored wheel build module. Pipeline, training-interface, and vLLM adapter tests passed **23 tests and two subtests**, with **five dependency/cache skips**. The numerical and actual-tokenizer tests require the restored training environment for a fresh complete run. See [environment reproduction](REPRODUCING_ENVIRONMENT.md) and [earlier measured evidence](TRAINING_BENCHMARK.md).
