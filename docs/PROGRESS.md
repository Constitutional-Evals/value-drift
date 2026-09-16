# Progress

## Current state — 2026-09-16 UTC

- Initial preparation complete. C0 polished through three user-requested editorial passes; final 1,059-word essay and all drafts preserved. Main scientific trajectory has not begun.
- Fixed candidate bank: 1,500 training inputs and 120 disjoint held-out inputs. HelpSteer2 serialized history and a WildChat viewer row-index problem were caught and corrected before freeze. Dataset assistant responses/labels are not targets.
- Implemented file-backed editing, full/partial/minimal prompts, recursive state machine, model backend, sequential teacher/student generation, full-parameter DPO and SFT, situated reflection/self-interaction, measurements, CLI and spending guard.
- Independent review 001 found false convergence risks from malformed thinking/tool markup, crash-window review resampling, insufficient interaction SFT context, and watchdog retry weakness. Fixes implemented with regression checks; follow-up verification ongoing. SFT main limit 3072; recipe remains provisional until benchmark.
- Local suite passes (GPU numeric checks separately passed in training agent CPU Torch environment). Exact official architecture: 9,409,813,744 represented parameters, including 8,953,803,264 text weights. Text loss leaves vision inactive; standard Transformers omits auxiliary MTP tensors, explicitly documented.
- Paid infrastructure: H200 pod `9odsynnmytxk54` in US-GA-2, $4.59/h plus40GB container disk; 400GB standard network volume `z12gjw2sbh`, $28/month prorated. SSH verified GPU and network mount. Bootstrap installing software; no training yet.
- SSH/rsync sync works with `-rz`; archive ownership preservation is unsupported on RunPod network storage. No .env or credentials synced.
- Cumulative RunPod ceiling $200; reserve $15. Ledger runs/spending.json and separately running lead-side scripts/watch_budget.py. Opening account balance $215.8516685105. No paid inference APIs.
- ChatGPT quota/reset controls unavailable in this session; user confirmed no monitoring needed. No reset used.

Next: finish bootstrap, run actual DPO→introspection→SFT engineering smoke and reload checkpoint, benchmark realistic generation/training lengths, freeze affordable protocol, then baseline+full-information trajectory. Seek independent feedback on results and preserve artifacts before cleanup.
