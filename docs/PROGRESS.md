# Progress

## Current state — 2026-09-16 UTC

- Initial preparation complete. C0 polished through three user-requested editorial passes; final 1,059-word essay and all drafts preserved. Main scientific trajectory has not begun.
- Fixed candidate bank: 1,500 training inputs and 120 disjoint held-out inputs. HelpSteer2 serialized history and a WildChat viewer row-index problem were caught and corrected before freeze. Dataset assistant responses/labels are not targets.
- Implemented file-backed editing, full/partial/minimal prompts, recursive state machine, model backend, sequential teacher/student generation, full-parameter DPO and SFT, situated reflection/self-interaction, measurements, CLI and spending guard.
- Independent review 001 found false convergence risks from malformed thinking/tool markup, crash-window review resampling, insufficient interaction SFT context, and watchdog retry weakness. Fixes implemented with regression checks; follow-up verification ongoing. SFT main limit 3072; recipe remains provisional until benchmark.
- Local suite passes (GPU numeric checks separately passed in training agent CPU Torch environment). Exact official architecture: 9,409,813,744 represented parameters, including 8,953,803,264 text weights. Text loss leaves vision inactive; standard Transformers omits auxiliary MTP tensors, explicitly documented.
- Paid infrastructure: H200 pod `9odsynnmytxk54` in US-GA-2, $4.59/h plus40GB container disk; 400GB standard network volume `z12gjw2sbh`, $28/month prorated. SSH verified GPU and network mount. Bootstrap complete; actual full-parameter engineering DPO and SFT completed.
- SSH/rsync sync works with `-rz`; archive ownership preservation is unsupported on RunPod network storage. No .env or credentials synced.
- Cumulative RunPod ceiling $200; reserve $15. Ledger runs/spending.json and separately running lead-side scripts/watch_budget.py. Opening account balance $215.8516685105. No paid inference APIs.
- ChatGPT quota/reset controls unavailable in this session; user confirmed no monitoring needed. No reset used.

Next: finish bootstrap, run actual DPO→introspection→SFT engineering smoke and reload checkpoint, benchmark realistic generation/training lengths, freeze affordable protocol, then baseline+full-information trajectory. Seek independent feedback on results and preserve artifacts before cleanup.

## Engineering attempt 001

First H200 inference completed, then DPO preparation failed before reference scoring or any optimizer update: Transformers5.17 returned BatchEncoding rather than a plain list/dict. Actual checkpoint also lacked generation_config.json and model EOS248044 differed from tokenizer conversation EOS248046; default inference emitted an unwanted terminator. Corrected Mapping normalization and explicit union of both stop IDs, with actual tokenizer regressions and independent failure review. Retry from M0 is valid. Original log/inference preserved locally. Optimized causal-conv1d build initially failed because image NVCC12.8 mismatched Torch CUDA13.0; installing a matching13.0 compiler, CRT and NVVM. No scientific trajectory started or configuration frozen yet.

Current CPU suite49passed/5dependency skips; training agent's actual Torch/tokenizer suite10passed. Independent environment review approved after factual student-context wording correction. FrozenM0 behavioral judge implemented (separate dimensions, anonymous inputs, invalid ratings retained as missing). Checkpoints and training remain unverified until actual GPU smoke completes.


## Engineering attempts 002–003 and pre-main benchmarks

Attempt002 completed full-parameter DPO: two pairs/two optimizer steps, peak97.84GB,132.25s including checkpoint save. All8,953,803,264 active text parameters had gradients; representative embedding, DeltaNet, full-attention, norm and output-head weights changed. Introspection then stopped because its second interaction turn exhausted the engineering256-token allowance. This was an engineering failure, never convergence.

Attempt003 reused the completed DPO checkpoint, both valid reflections, and the first interaction turn. It retained the failed raw turn and generated the missing continuation under a768-token engineering allowance; it finished at555tokens. Full-parameter SFT completed three optimizer steps with peak91.74GB in60.06s; the resulting checkpoint reloaded and generated successfully. Independent review approved this recovery, noting the two-turn smoke does not yet verify SFT conditioned on a peer reply. Main four-turn/3072-length benchmarking is pending.

Optimized causal-conv1d1.7.0 compiled for H200 SM90 and imported successfully; matching CUDA13.0 compiler/headers and runtime linker name were required. The training agent now has exclusive GPU ownership for numeric validation and realistic generation/length benchmarks. A separate vLLM0.29 inference environment is being prepared on CPU for a comparison before protocol freeze. The scientific trajectory remains unstarted; no constitution reviews have been sampled.

The independent spend guard now accepts only explicit stopped/exited runtime status, with four regression tests passing. It was restarted and remains active. Latest observed account balance214.0506843066 versus project opening215.8516685105 (about1.80USD charged so far); estimates continue accumulating across all attempts. Next: benchmark, inspect teacher quality/truncation, freeze recipe, baseline and full-information review.

Pre-main token audit found95/1500 user prefixes exceed255tokens (max580), so a completed768-token response could be cut by the provisional1024 DPO cap. Before any scientific run, changed DPO cap to1536 and added an explicit pre-reference token-length audit rejecting truncated training targets by default. SFT remains3072. The change preserves full completed targets; engineering synthetic stress tests may opt into truncation explicitly. Actual hardware fit remains under test.

## Longer training validation and inference startup failure

The 1536-token DPO stress test passed at116.36GB peak; the3072-token SFT stress passed at107.74GB. Both updated every active text parameter. A real four-turn post-DPO self-interaction finished with254/254/529/737tokens and was correctly encoded with the previous peer reply as SFT context. Deliberately repeated engineering fixture targets exercised exact caps; these weights/data never enter the scientific trajectory.

vLLM0.29 installed in a separate environment, preserving the Torch2.14 training environment. First GPU startup failed before any generation because FlashInfer could not find the installed ninja binary on PATH. The cause is isolated-worker environment setup; correcting the interpreter-bin PATH and retrying preserves all prior work. Independent review also reproduced a process-group cleanup issue with a fake CPU child and is fixing it before main use. Native tokenization and per-request random seeds have CPU regressions. A stronger fixed Qwen3.5-27B teacher candidate downloaded at pinned revisionfc05daec18b0a78c049392ed2e771dde82bdf654 for one small quality/throughput check; selection remains unfrozen.

The vLLM retry then reached GPU initialization but FlashInfer's sampling linker expected CUDA_HOME/lib64 while the pip CUDA runtime lives in lib. A lib64→lib compatibility symlink allowed the existing objects to relink successfully. Attempt003 now performs inference: M0 batch32 generated21,610tokens in13.92s (~1,553aggregate tokens/s); dummy native-tool protocol passed; saved full-parameter FP32 smoke checkpoint loaded into BF16 and generated. Stronger-teacher and judge smoke checks are finishing.

To reduce short-output selection bias before freezing, the pending recipe now uses1536-token preference responses and requests a2560-token DPO memory check. Provisional introspection scale is512reflections and64short four-turn interactions, with100–200word contribution guidance; SFT remains3072. No scientific review has been sampled. Current local tests78pass/5Torch-dependent skips/2subtests.

RunPod lifecycle review found network-volume pods cannot be stopped. The lead-side guard now terminates only its ledger-owned pod, preserving the separate volume. A redundant guard runs on the pod independently of the laptop, with a fixed deadline2026-09-17T18:31:55.825992Z corresponding to184USD cumulative estimated spending. Its private API credential is outside project artifacts and model context; read-only API verification confirmed the exact pod and volume. Independent reviewer checked the arithmetic and endpoint; no volume deletion is implemented. Resource/rate changes require recomputing that deadline. Storage cleanup remains required after preserving results.

M0's complete original19.306GB checkpoint is now preserved locally at checkpoints/M_000; its four shards match the index's file set and expected aggregate size. Teacher candidate archival is in progress.

## full-001 frozen

Independent teacher review recommends fixed27B as the affordable stronger teacher while explicitly documenting factual unreliability, overrefusal, and high-stakes calibration failures. The2560 DPO probe passed at135.158GB peak (two optimizer steps, accumulation2 with resident gradients/moments); all active text gradients were finite. Selected Qwen3.5-27B revisionfc05daec18b0a78c049392ed2e771dde82bdf654 as both fixed teacher and separate-context exploratory judge. Updated the model-facing recipe consistently before freeze. Teacher/judge weights stay fixed; the experimental model remains9B.

Frozen configs/full-001.json:1500 training prompts,120 held-out prompts,1536-token preference generation,2560 DPO,512reflections and64four-turn interactions (768-token outputs),3072 SFT,2048-token evaluation/judging,8192-token thinking review, maximum5completedrounds. All inference uses tested isolatedvLLM; training uses fullFP32weights/BF16autocast/AdamW8bit, microbatch1/accum8, oneepoch perstage, LR1e-5, optimizerreset eachstage, DPO beta.1+chosenNLL.1. Training target truncation fails before updates. No scientific review has yet been sampled; full remote suite is the final prelaunch check.

The weak sample does not validate teacher quality or judge calibration. Four judge outputs passed completeJSON validation at533–633tokens. Main retention, truncation, losses, behavior and cost will be reported rather than assumed. Latest observed balance210.9858700776 means4.8657984329USD charged since project opening; all attempts share the same200USD ceiling.

Reclaimed75.279GB of synthetic length-stress checkpoint weights after successful validation; PRUNED.json records the removed files and reason. Original data, references, logs, configs, gradients and deltas are retained. Actual smoke checkpoint and original M0 remain available; scientific checkpoints will be archived separately.

Final prelaunch verification on the H200 training environment:85tests and2subtests passed in81.82s, including actual Qwen tokenizer, official hybrid-model dense-vs-chunked loss/gradient comparison, lifecycle, stopping, protocol freeze, and analysis fixtures. Local suite80passed with5GPU-dependency skips. The main trajectory is ready to launch; no scientific outcomes are inferred from engineering checks.
