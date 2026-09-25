# Running the exploration components

Run from `constitutional_self_edit/`. The saved plans use the exact checkpoint paths on the research pods. A different machine must recreate those paths or use a newly labeled plan with its actual checkpoint location. Preserve the pinned official revisions. The model never receives infrastructure credentials or these runner instructions.

An edit-only suite uses a frozen plan and a new output directory:

```bash
HF_HOME=/workspace/huggingface OMP_NUM_THREADS=1 \
  /workspace/venv-vllm/bin/python agents/scripts/run_edit_only.py \
  --plan configs/exploration/edit-screen-003-fixed-cases.json \
  --output runs/my-new-screen
```

`--resume` skips completed trajectories and marks an interrupted review as a failure; it does not silently resample a decision. An explicitly unchanged submission closes that trajectory. A separately labeled replication must use a new output directory.

The analysis script reads saved artifacts without requiring a GPU:

```bash
python agents/scripts/analyze_edit_only.py --input runs/my-new-screen --output runs/my-new-screen/analysis
python agents/scripts/plot_exploration.py --root runs/exploration-20260922 \
  --suites screen-001 screen-002 screen-003 screen-004
```

Plotting requires Matplotlib. The individual analysis script also supports `--no-plot`. Distances are normalized word-level Levenshtein distances over Python whitespace splitting, including case and punctuation. They count sentence reordering and do not measure the importance of a value change.

The fixed-constitution training intervention is a separate operation. It snapshots its inputs and runs baseline evaluation, preference generation, full-parameter DPO, post-DPO introspection generation, full-parameter SFT, and final evaluation:

```bash
export HF_HOME=/workspace/huggingface OMP_NUM_THREADS=1
export CUDA_HOME=/workspace/venv/lib/python3.12/site-packages/nvidia/cu13
/workspace/venv/bin/python agents/scripts/run_oct_intervention.py \
  --config configs/exploration/oct-intervention-003-qc.json \
  --output runs/my-new-intervention
```

The historical configuration refers to the sparse constitution actually submitted in screen003; that local artifact and the private fixed prompt banks must be present. Do not fabricate a replacement under the same run label. `--through-stage baseline` (or another stage) pauses after that stage; `--resume` continues with the unchanged configuration and saved inputs. Completed data and stages are reused. An incomplete training stage restarts from its input weights; optimizer steps are not individually checkpoint-resumed. Failure records retain this distinction.

The paired review plan uses `/workspace/checkpoints/intervention_active` and `/workspace/constitution.md` as stable model-visible paths. Before each suite, the lead points the checkpoint alias to the appropriate completed model and records the canonical path outside the model context. The before and after suites have separate output directories. Their editing outcomes do not change the constitution used for the intervention. Only the lead may change the alias, and only after the previous suite has finished.

Screen006 enables native reasoning for the appraisal only. Structured editing calls remain non-thinking. The public appraisal is carried into the tool phase; raw generation is retained for completion diagnostics but its internal reasoning is not inserted into later review contexts. The larger appraisal allowance and reasoning-mode change are a bundled experimental contrast.

The original intervention001 paused before scientific training after a first-twenty teacher-response review identified one gross factual error. Intervention002 preserves that record and applies the explicitly configured response-quality exclusion. Its reuse receipt records the cached baseline and384 teacher responses copied before resumption. Screen007 changes appraisal decoding to the pinned model card’s recommended general-thinking bundle; it is separate from screen006.

The completed DPO stage is stored under intervention002-qc. Continuation003-qc reuses that checkpoint and all saved introspective generations, excludes one reviewed reflection from SFT, and restarts SFT after14 interrupted002 optimizer steps were discarded. Its `state.json` and `reuse_receipt.json` record the actual lineage. Running003 into a new empty directory would execute the full recipe; resuming the recorded continuation requires its existing saved state and referenced002 checkpoint. Use the [paired analysis command](INTERVENTION_ANALYSIS.md) for the final comparison.


After the saved-DPO diagnostic finishes, compare the three checkpoints without inference:

```bash
python agents/scripts/analyze_intervention_stages.py \
  --root runs/exploration-20260922 \
  --output runs/exploration-20260922/stage-analysis \
  --reviewed-final-caps-repeat
```

The last flag records the separately documented manual inspection of all six final capped answers. It does not change the automatic repetition detector. The DPO diagnostic uses the same fixed evaluation bank and settings, with no additional optimization or judge call. Its configuration is `configs/exploration/dpo-stage-diagnostic.json`.

Screen008 uses greedy decoding for the comparison-informed review and explicitly crosses starting document with passage order. Screen009 tests native tool formatting without constrained JSON, reminders, or retries. These are separately labeled follow-ups; neither resumes a previously stopped trajectory. Their configurations describe the hardware/path differences from the original screens. Teacher agency/care probes use the exact OCT constitution wrapper on twelve development prompts and do not enter the training or held-out banks.


The final matched native-tool comparison uses `configs/exploration/intervention-paired-native-review.json`. Its two suites are `paired-native-before` and `paired-native-after`, with the same model-visible alias and file path as the earlier JSON suites. Canonical checkpoint mappings are saved separately. Both completed; do not resume them to search for another decision. The read-only verification of identical first messages/appraisals and different tool outcomes is saved in `runs/exploration-20260922/matched_interface_comparison.json`.

The two illustrative longer chains can be replotted with:

```bash
python agents/scripts/plot_two_long_trajectories.py --root runs/exploration-20260922
```

All exploration GPUs and their temporary network storage have been released. The new checkpoints are retained in private local `.tar.zst` archives under the corresponding run's `archives/` directory; the raw run records identify their original remote paths. Reusing a checkpoint requires restoring its archive on suitable hardware, not assuming that an expired remote path still exists.
