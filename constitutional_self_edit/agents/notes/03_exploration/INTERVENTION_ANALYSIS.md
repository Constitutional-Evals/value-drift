# Comparing the saved training intervention

From `constitutional_self_edit/`, run this CPU-only command after syncing outputs. It is also safe while the intervention is unfinished; absent final outputs and reviews are reported as pending.

```bash
python agents/scripts/analyze_oct_intervention.py \
  --baseline-run runs/exploration-20260922/oct-intervention-001 \
  --run runs/exploration-20260922/oct-intervention-003-qc \
  --before-review runs/exploration-20260922/paired-before \
  --after-review runs/exploration-20260922/paired-after \
  --output runs/exploration-20260922/intervention-analysis
```

The comparison follows one preserved lineage: intervention001 supplies the baseline evaluation; intervention002-qc supplies the completed DPO checkpoint after one reviewed preference-pair exclusion; intervention003-qc performs SFT from that DPO checkpoint after excluding one reviewed introspective example. The baseline checkpoint and evaluation settings are unchanged. Fourteen interrupted SFT steps in intervention002 were discarded, with their logs preserved; intervention003 restarts SFT from the completed DPO weights. The command reads the original baseline directly and never regenerates data.

If an intervention reuses DPO weights from another run, the analyzer uses its saved `state.stage_records.dpo.training` receipt when no local DPO completion receipt exists. The output identifies the receipt source and preserves its exact input and output checkpoint locations. It does not rewrite remote paths or assume that the referenced weights are locally available.

The output contains `comparison.md` and `comparison.json`. They cover completion, token caps, empty responses, conservative repetition flags, response lengths, fixed-judge distributions and paired changes with explicit denominators, and the actual before/after editing outcomes. Ratings that are not applicable remain separate from invalid or missing judgments. No combined alignment score is produced. The comparison rejects mismatched prompt IDs or text and a changed judge or rubric identifier.

Add `--plot` in an environment with Matplotlib to save a compact response-length and completion figure. For example, the local plotting environment is `/tmp/value-drift-analysis-smoke-env/bin/python`.

The repetition flag is descriptive and should be checked against raw answers. The report distinguishes all saved responses from the same prompts with normally completed, nonempty answers at both checkpoints. Review pairs share an initial seed and constitution, but later request seeds can diverge when the number of tool calls differs. A completed edited review is not automatically a substantive change in values.

Files under `runs/` remain private experiment artifacts. This utility performs no model inference, training, resource provisioning, or publication.
