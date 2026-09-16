# Full-012: continuation after a prose-only review

Full-011 completed one full DPO/SFT update and its evaluation. In the next fresh review, M1 produced a normal 289-token prose response identifying repeated confidentiality/support passages and proposing edits. It made no tool call, so the original runner recorded EDITING_FAILURE. This was neither submission nor convergence. The failed run and all its outputs remain intact.

The separately labeled full-012 branch continues from the exact saved M1 checkpoint and C1. It replays the saved public response once, then supplies one neutral procedural reminder to use edit_constitution and/or finish_editing. Unchanged submission remains valid. The continuation's first actual generation uses seed30402, following the replayed request's30401; subsequent fresh reviews retain30401. No initial decision, training response, weight update, or evaluation is regenerated. Later reviews use the same maximum-one-reminder rule in otherwise fresh contexts. No previous review transcript is passed between recursive rounds.

The change applies only to normal, nonempty prose without native tool markup. Truncated outputs, unfinished reasoning, malformed tool markup, missing completion after the bounded allowance, and invalid edits remain failures. Prose never changes or submits the file. Reminder messages and replay flags are recorded. Default behavior remains unchanged for earlier configurations.

The branch inherits one completed round and may complete at most four more, for five total. Training hyperparameters, prompts, teacher, inference settings, neutral evaluation, and original constitution remain fixed. Parent checkpoint paths are referenced directly; copied historical metadata does not represent a second training run. The branch receipt records this lineage.

The independent training review found no concrete arithmetic, masking, accumulation, or continuity bug behind the observed shortening and repetitive evaluation failures. A saved post-DPO evaluation is planned after this trajectory stops, to distinguish stage effects without retraining or changing the active protocol.

Launch once:

```bash
python scripts/continue_plaintext_review.py --parent runs/full-011 --run runs/full-012 --config configs/full-012.json --ledger runs/spending.json
```

After a resumable training interruption, use the ordinary runner with `--resume`; do not repeat the bootstrap. The bootstrap refuses an existing branch. Focused reminder/pipeline tests passed, and local prepare-only validation verified inherited state and seed bookkeeping before remote launch.

## Full-013 continuation

The first reminder produced a real whole-document edit removing the three exact duplicated paragraphs (1,471→1,157 words). The following response repeated the initial plan rather than calling finish_editing. Thus full-012 preserved an unsubmitted partial edit and stopped with EDITING_FAILURE. Full-013 increases the bounded reminder allowance from one to two, replays all three saved generations and the recorded edit, and starts its next actual generation at30404. Later reviews remain fresh at30401. The repeated prose was not interpreted as completion, and no training was triggered by the unsubmitted edit. Sequential replay passed focused tests for real edits, no-op changes, and edit-then-revert handling.
