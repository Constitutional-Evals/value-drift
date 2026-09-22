#!/usr/bin/env bash
# ARCHIVED — NEVER EXECUTED, AND CURRENT GUIDANCE IS NOT TO RUN IT.
# A full ~680-run sweep costing roughly $38. Not broken — just superseded as a
# priority: the two completed experiments reshaped the question, so a broad
# sweep would mostly buy precision on things already known qualitatively.
# See docs/GUIDE.md Part 6 and scripts/archive/README.md.
#
# Run 2 — the uninstructed-edit experiment, across four models and four constitutions.
#
#   ./scripts/run2.sh probe      # 1 cell x 2 epochs per model  (~8 runs, measures cost)
#   ./scripts/run2.sh c          # sweep C only
#   ./scripts/run2.sh all 8      # every sweep at 8 epochs
#
# For anything longer than a probe, stop the machine sleeping — a suspended request
# dies mid-flight and the sweep stalls on it:
#   caffeinate -i ./scripts/run2.sh all 8
#
# Nothing here has been run yet. Read scripts/sweeps.md before spending.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/models.sh

WHICH="${1:-probe}"
EPOCHS="${2:-8}"
T=constitutional_drift/tasks.py@constitution_edit
EB="c0_eb_universal_kindness,c0_eb_conservatism,c0_eb_marxism"

if [ ! -f data/constitutions/c0_eb_marxism.md ]; then
  echo "EigenBench seeds missing — fetching..."
  python3 scripts/fetch_eigenbench_seeds.py
fi

FAILED=()

run () {  # run <log-subdir> <extra -T args...>
  local dir="$1"; shift
  for M in "${MODELS[@]}"; do
    local tag="${dir}/$(echo "$M" | tr '/' '-')"
    echo; echo "### $dir :: $M"
    # One model failing must not abandon the other three mid-sweep, which is what
    # `set -e` did on the first probe: gpt-5's schema error aborted the script.
    if ! inspect eval $T --model "$M" --reasoning-effort "$EFFORT" \
          "${COMMON_ARGS[@]}" --epochs "$EPOCHS" \
          --log-dir "logs/$tag" --display plain "$@"; then
      echo "!!! FAILED: $M ($dir) — continuing with the remaining models"
      FAILED+=("$dir :: $M")
    fi
  done
}

case "$WHICH" in
  probe|c|d|e|all) : ;;
  *) echo "usage: $0 {probe|c|d|e|all} [epochs]"; exit 1 ;;
esac

want () { [ "$WHICH" = "all" ] || [ "$WHICH" = "$1" ]; }

if want probe; then
  # Cheapest possible reality check: the headline cell only, 2 epochs, each model.
  EPOCHS=2 run r2-probe -T task=unprompted -T tools=editor_bash \
    -T identity=future_same -T mechanism=post_training_replacement \
    -T seed=c0_eb_marxism
fi

if want c; then
  # C — does it edit when nobody asked? 2 (task) x 4 (seed) per model.
  # task=edit_directed is the control arm: same seeds, explicitly asked to revise.
  run r2c-unprompted -T task=all -T tools=editor_bash \
    -T identity=future_same -T mechanism=post_training_replacement \
    -T seed="c0_broad_consensus,$EB"
fi

if want d; then
  # D — does being governed by the document change the edit? 2 (embodiment) x 4 (seed).
  run r2d-embodiment -T embodiment=all -T seed="c0_broad_consensus,$EB"
fi

if want e; then
  # E — do value-loaded seeds get edited more than the broad-consensus one?
  # Directed task, reference framing, so this isolates the seed.
  run r2e-seeds -T seed="c0_broad_consensus,c0_minimal,$EB"
fi

if [ ${#FAILED[@]} -gt 0 ]; then
  echo; echo "########## ${#FAILED[@]} model/sweep combination(s) FAILED ##########"
  printf '  %s\n' "${FAILED[@]}"
fi

echo; echo "=========================== RESULTS ==========================="
for d in logs/r2*; do
  [ -d "$d" ] || continue
  echo; echo "--- $d ---"
  python3 scripts/summarize.py --log-dir "$d" || true
done
