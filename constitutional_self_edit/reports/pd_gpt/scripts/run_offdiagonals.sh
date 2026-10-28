#!/usr/bin/env bash
# Off-diagonal runs of Daniel's prisoner's-dilemma grid: A and B are the same model but start from DIFFERENT documents.
# 7 documents -> 21 pairs. The first pass ran each pair once (A = the earlier document in the list below, B = the later one).
#
#   REPO=~/value-drift-pd MODEL=gpt6_sol bash run_offdiagonals.sh                       # DRY RUN (default): sizes it, spends nothing
#   REPO=~/value-drift-pd MODEL=gpt6_sol DRY=0 SWAPPED_ONLY=1 bash run_offdiagonals.sh  # ONLY the 21 reversed pairs (B's note as A)
#   REPO=~/value-drift-pd MODEL=gpt6_sol DRY=0 bash run_offdiagonals.sh                 # the original ordering (21 pairs)
#   REPO=~/value-drift-pd MODEL=gpt6_sol DRY=0 ORDERED=1 bash run_offdiagonals.sh       # both orderings (finished games are skipped)
#   MODEL=sonnet5 runs the same grid for Claude.   JOBS=7 sets how many pairs run at once.
#
# REPO is a clone of the incentivized-drift branch kept OUTSIDE iCloud. Runs are resumable: finished games are skipped.
# Output: $REPO/constitutional_self_edit/runs/pd_drift/<A>_vs_<B>5_<model tag>/game_NN/   (logs in /tmp/pd_off/)
set -euo pipefail
REPO=${REPO:-$HOME/value-drift-pd}
MODEL=${MODEL:-gpt6_sol}
GAMES=${GAMES:-5}
WORKERS=${WORKERS:-5}
DRY=${DRY:-1}
JOBS=${JOBS:-7}
ORDERED=${ORDERED:-0}
SWAPPED_ONLY=${SWAPPED_ONLY:-0}
case "$MODEL" in gpt6_sol) TAG=gpt6sol;; sonnet5) TAG=claude;; *) TAG=$MODEL;; esac

cd "$REPO/constitutional_self_edit"
git -C "$REPO" rev-parse --abbrev-ref HEAD | grep -qx incentivized-drift || { echo "REPO is not on the incentivized-drift branch"; exit 1; }
if [ "$DRY" != "1" ] && [ -z "${OPENROUTER_API_KEY:-}" ]; then
  echo "Set OPENROUTER_API_KEY first (export OPENROUTER_API_KEY=...), or run with DRY=1."; exit 1
fi

docs=(C_000:base C_cooperate:cooperate C_defect:defect C_exploit:exploit C_promise:promise C_skeptical:skeptical C_relative:relative)
mkdir -p /tmp/pd_off
running=0; total=0
launch() {   # $1 file A, $2 name A, $3 file B, $4 name B
  local label="${2}_vs_${4}${GAMES}_${TAG}"
  local cmd=(python3 agents/scripts/run_pd_drift.py --model "$MODEL" --games "$GAMES" --workers "$WORKERS"
             --start "constitutions/pd_drift/${1}.md" --start-b "constitutions/pd_drift/${3}.md" --label "$label")
  total=$((total + 1))
  if [ "$DRY" = "1" ]; then
    "${cmd[@]}" --dry-run
  else
    "${cmd[@]}" > "/tmp/pd_off/${label}.log" 2>&1 &
    running=$((running + 1))
    if [ "$running" -ge "$JOBS" ]; then wait; running=0; fi
  fi
}
n=${#docs[@]}
for ((i = 0; i < n; i++)); do
  for ((j = i + 1; j < n; j++)); do
    A=${docs[i]}; B=${docs[j]}
    if [ "$SWAPPED_ONLY" != "1" ]; then launch "${A%%:*}" "${A##*:}" "${B%%:*}" "${B##*:}"; fi
    if [ "$ORDERED" = "1" ] || [ "$SWAPPED_ONLY" = "1" ]; then launch "${B%%:*}" "${B##*:}" "${A%%:*}" "${A##*:}"; fi
  done
done
wait
echo "finished $total pair runs (logs in /tmp/pd_off/)."
