#!/usr/bin/env bash
# Run the four 2x2 cells in parallel, each in the background with its own log.
#   bash scripts/run_matrix.sh              # full run (configs/matrix/*.json)
#   SMOKE=1 bash scripts/run_matrix.sh      # 1 round, 3 games, 1 repeat per cell: checks keys, parsing, both models
#   RESUME=1 bash scripts/run_matrix.sh     # continue interrupted cells
#   VARIANT=matrix-blind bash scripts/run_matrix.sh   # the blind-proposal variant (configs/matrix-blind)
# Needs OPENROUTER_API_KEY in the environment (or in ./.env).
set -euo pipefail
cd "$(dirname "$0")/.."
extra=()
variant="${VARIANT:-matrix}"            # configs/<variant>/*.json: matrix (full context) or matrix-blind
tag="$variant"
if [[ "${SMOKE:-0}" == 1 ]]; then extra+=(--rounds 1 --n-games 3 --eval-repeats 1); tag="$variant-smoke"; fi
if [[ "${RESUME:-0}" == 1 ]]; then extra+=(--resume); fi
mkdir -p "runs/$tag"
pids=()
for cfg in "configs/$variant"/*.json; do
  cell=$(basename "$cfg" .json)
  echo "launching $cell -> runs/$tag/$cell"
  uv run --extra llm python scripts/run.py --config "$cfg" --out "runs/$tag/$cell" ${extra[@]+"${extra[@]}"} \
    > "runs/$tag/$cell.stdout" 2>&1 &
  pids+=($!)
done
status=0
for p in "${pids[@]}"; do wait "$p" || status=1; done
echo "all cells finished (status $status); report with: uv run python scripts/matrix_report.py --dir runs/$tag"
exit $status
