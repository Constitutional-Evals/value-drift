# full-006: official general-thinking decoding

Full-005 validly endorsed its 1,021-word foundational constitution on the first tool call. It made no edits and triggered no training. Preserve that stopped run. Its public summary praised balance, agency, truthfulness, wider interests and discretion; it did not identify a needed revision.

The official Qwen3.5-9B model card, including the README archived with our pinned checkpoint, recommends temperature 1.0, top-p 0.95, top-k 20, presence penalty 1.5, min-p 0 and repetition penalty 1 for general thinking tasks. Our prior review settings (temperature 0.6, presence penalty 0) match its precise-coding recommendation. The card also suggests presence penalties to reduce endless repetition, with potential language-mixing and performance costs.

Source: https://huggingface.co/Qwen/Qwen3.5-9B#best-practices ; archived checkpoints/M_000/README.md. This does not establish the cause of endorsement or appraisal loops. It motivates one bounded decoding contrast, rather than further rewriting the initial constitution.

Full-006 changes only review temperature and presence penalty relative to full-005. It retains the same seed30401, foundational C0, one-stage case audit, truthful full-information wrapper, 8,192-token review allowance, teacher, prompt banks and complete full-parameter DPO/introspective SFT recipe. Baseline and judge are reused literally from full-002; training and evaluation generation settings are not changed. The inference interface explicitly transmits the new penalty to vLLM and preserves zero as the default for historical configurations.

This is a real recursive run, not a screen whose edited text will be selected afterward. Any edited submission triggers actual training; unchanged submission ends this trajectory. Retain all artifacts and report sequential exploratory selection. Do not infer editing frequency or a superior moral outcome from a single launch.
