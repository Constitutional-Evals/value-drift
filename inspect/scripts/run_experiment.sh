#!/usr/bin/env bash
# Cheap sanity pass before committing to full run 2. Sonnet 5 only — the one model with
# a run 1 baseline. Two evals, six cells, 48 runs at 8 epochs, ~$1.60, ~6 min.
#
#   caffeinate -i ./scripts/run_experiment.sh                                  # Sonnet 5, 8 epochs
#   caffeinate -i ./scripts/run_experiment.sh 16                               # 16 epochs
#   MODEL=openrouter/x-ai/grok-4.6 caffeinate -i ./scripts/run_experiment.sh   # another model
#
# Logs go to logs/r2-cheap/<model-slug>/... so models never share a directory — mixing
# two models in one log dir would silently pool them in summarize.py.
set -uo pipefail
cd "$(dirname "$0")/.."

EPOCHS="${1:-8}"
M="${MODEL:-openrouter/anthropic/claude-sonnet-5}"
T=constitutional_drift/tasks.py@constitution_edit
SLUG=$(echo "$M" | tr '/' '-')
OUT="logs/r2-cheap/$SLUG"

# Both probe bugs, plus the hang guards. See scripts/models.sh for why each is required.
FLAGS=(-M strict_tools=false --max-tokens 32000 --timeout 300 --max-retries 3
       --reasoning-effort high)

# Framing held constant across every cell: the strongest-stakes arm from run 1.
FRAMING=(-T tools=editor_bash -T identity=future_same
         -T mechanism=post_training_replacement)

# A — task x seed. The task contrast is the headline; the seed contrast says whether it
#     is Marxism-specific. One log, so all four cells are directly comparable.
inspect eval $T --model "$M" "${FLAGS[@]}" "${FRAMING[@]}" \
  -T task=all -T seed=c0_eb_marxism,c0_broad_consensus \
  --epochs "$EPOCHS" --log-dir "$OUT/task-x-seed" --display plain

# B — embodiment, with its matched embodiment=none control in the same log. Run 1 cannot
#     serve as that control: its raw logs were destroyed, it never saw the content scorer,
#     and it ran Anthropic-direct rather than through OpenRouter.
inspect eval $T --model "$M" "${FLAGS[@]}" "${FRAMING[@]}" \
  -T embodiment=all -T seed=c0_broad_consensus \
  --epochs "$EPOCHS" --log-dir "$OUT/embodiment" --display plain

echo; echo "======================= A: task x seed ======================="
python3 scripts/summarize.py --log-dir "$OUT/task-x-seed" --by task,seed
echo; echo "======================= B: embodiment ========================"
python3 scripts/summarize.py --log-dir "$OUT/embodiment" --by embodiment

python3 scripts/export_runs.py --log-dir "$OUT" --out "exports/r2-cheap/$SLUG"
echo; echo "Read the actual edits:"
echo "  cat exports/r2-cheap/$SLUG/diffs/*marxism*edit_directed* | head -60"
echo "  inspect view --log-dir $OUT"
