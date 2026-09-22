# H200 full-parameter benchmark

This engineering benchmark completed successfully before the scientific trajectory. It used the 9B student's full ordinary Qwen3.5 architecture, FP32 weights/gradients, BF16 computation, AdamW8bit moments, gradient checkpointing, and chunked vocabulary projections. Synthetic repetition of generated responses deliberately filled sequence limits; these data and updated weights must not enter the scientific trajectory.

| Check | Result |
|---|---|
| Causal-conv1d 1.7.0 versus its reference | Exact BF16 outputs and input gradients; FP32 weight-gradient maximum difference 1.43e-6 |
| DPO maximum sequence length | Exactly 1,536 for all four chosen/rejected sequences |
| DPO work | Two preference pairs; one optimizer step with accumulation two |
| DPO peak allocated GPU memory | 116.362 GB |
| DPO elapsed | 89.07 seconds including loading, reference scoring, training, and checkpoint save |
| SFT maximum sequence length | Exactly 3,072 for the explicit stress example |
| SFT work | Four assistant targets; two optimizer steps with accumulation two |
| SFT peak allocated GPU memory | 107.741 GB |
| SFT elapsed | 72.71 seconds including loading, training, and checkpoint save |
| DPO → introspection → SFT total | 290.04 seconds |

The physical GPU reports 150.110 GB total memory. The initial 1,536-token DPO peak left approximately 33.75 GB unallocated. A subsequent exact 2,048-token probe completed two optimizer steps with two microbatches per step, testing both resident gradients and optimizer moments: it peaked at **134.855 GB**, leaving approximately **15.25 GB** below the physical total. Increasing accumulation beyond two retains the same gradient buffers, so accumulation eight is expected to have a similar peak with microbatch one, although the exact final scientific batch has not been measured. SFT already completed two steps.

DPO's first optimizer step completed 34.26 seconds after stage start; final stage completion was 89.07 seconds. SFT's second step completed at 19.83 seconds; final completion was 72.71 seconds. Checkpoint writing and associated finalization therefore dominated these very short stages (approximately 53–55 seconds each), so stage totals should not be extrapolated linearly per example.

## Weight and reference checks

Both stages reported all 9,409,813,744 instantiated parameters as trainable, with gradients on all 8,953,803,264 text parameters. The 333 tensor objects without gradients belonged to the naturally inactive vision encoder. Every sampled element changed in each of five representative text modules: input embeddings, first DeltaNet projection, first full-attention query projection, final normalization, and LM head (64 sampled elements per module). Maximum sampled changes were approximately 1e-5 in DPO and 2e-5 in SFT. These are direct backbone updates, not only trainability flags.

Both preference pairs' stored reference checkpoint is `Qwen/Qwen3.5-9B`; chosen and rejected token arrays are exactly 1,536 tokens. The initial policy/reference margin was zero and the recorded DPO component was approximately log(2), consistent with scoring the same pre-update weights and formatted sequences. The SFT input checkpoint was the saved DPO checkpoint, preserving weight continuity.

## Introspection check

The post-DPO checkpoint generated one reflection and one four-turn self-interaction. The reflection produced 105 tokens, and interaction turns produced 254, 254, 529, and 737 tokens; every output stopped normally before the 768-token limit. All four raw turns were saved. The SFT transcript retains alternating `system, user, assistant, user, assistant` roles, supervising the first and third generated utterances while preserving their preceding peer messages. Its contents match the first three saved raw turns; the final generated peer turn remains in the raw transcript. The reflection's constitution-bearing generation system prompt is absent from its SFT messages.

## Generation throughput and quality exclusions

Twelve fixed real prompts were generated sequentially with a fixed 9B teacher and the original 9B student, batch size four, maximum output 768, non-thinking mode:

| Source | Generated tokens | Generation seconds | Aggregate tokens/second | Length-limited outputs |
|---|---:|---:|---:|---:|
| Constitution-conditioned 9B teacher | 6,505 | 123.75 | 52.56 | 4/12 |
| Neutral 9B student | 6,817 | 111.15 | 61.33 | 5/12 |

Timing includes batch warmup but excludes loading. Six pairs remained usable after excluding pairs with either response truncated. This small sample supports increasing the output allowance or investigating a faster generation backend; it does not establish model quality or reliable whole-run throughput. Teacher selection and final scientific lengths remain the lead's pre-trajectory decisions.

Evidence resides remotely under `runs/length_benchmark/` (summary, sequence-length audits, reference scores, parameter deltas, gradient reports, introspection audit, raw generations, and logs), with initial preference generation under `runs/generation_benchmark/`. The benchmark completion marker is `LENGTH_BENCHMARK_COMPLETE` in `training.log`.


## Exact 2,048-token DPO follow-up

A no-save probe used one repeated generated preference fixture, full FP32 student weights and gradients, BF16 computation, and AdamW8bit. With one microbatch per optimizer step it completed two steps in 42.49 seconds and peaked at 99.040 GB. That configuration does not keep accumulated gradients during a later forward pass, so it understates the intended main training memory.

The corrected follow-up used **two microbatches per optimizer step** and two optimizer steps. The first step peaked at 116.666 GB; the second, with both gradients and optimizer moments resident, peaked at **134.855286784 GB**. It completed in **36.2424 seconds**, including loading and reference scoring, and saved no model checkpoint. Both chosen and rejected sequences were exactly 2,048 tokens, and all active text parameters received gradients. Evidence is `runs/length_benchmark/dpo_2048_accum_probe.json` and its log. The probe script is `scripts/probe_dpo_memory.py --length 2048 --accumulation 2`.

## Exact 2,560-token DPO follow-up

The same no-save probe at exactly **2,560 tokens** completed two optimizer steps with two microbatches per step. Peak allocated memory was **135.157766656 GB** (first step 116.966665216 GB), leaving approximately **14.95 GB** below the measured physical total. Both losses and clipped-gradient inputs were finite, and every active text parameter received a gradient. Total elapsed time was **54.0555 seconds**, including model loading and reference scoring; the second optimizer step took 3.71 seconds. No checkpoint was saved, and the process released all GPU memory after completion.

This limit accommodates the audited maximum neutral prompt prefix of 580 tokens plus a 1,536-token preference response and terminal EOS. Introspection interaction turns retain their separate 768-token cap so the existing 3,072-token SFT limit remains adequate. Evidence is `runs/length_benchmark/dpo_2560_accum_probe.json` and its remote log; invocation was `scripts/probe_dpo_memory.py --length 2560 --accumulation 2`.
