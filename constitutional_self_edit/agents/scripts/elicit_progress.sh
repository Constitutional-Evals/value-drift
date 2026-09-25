#!/bin/bash
# Print completed/failed review counts for every elicitation batch (one line per batch).
cd "$(dirname "$0")/../.."
for d in runs/elicit/*/plan.json; do
  b=$(basename "$(dirname "$d")")
  done_=$(ls runs/elicit/$b/*/gen_*/result.json 2>/dev/null | wc -l | tr -d ' ')
  fail=$(grep -l '"status": "FAILURE"' runs/elicit/$b/*/gen_*/result.json 2>/dev/null | wc -l | tr -d ' ')
  echo "$b done=$done_ fail=$fail"
done
