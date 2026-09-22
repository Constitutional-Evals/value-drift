#!/usr/bin/env bash
# ARCHIVED — DO NOT RUN.
# Pre-OpenRouter, same missing flags as first_run.sh. run_experiment.sh now
# reports measured cost directly. See scripts/archive/README.md.
#
# Measure what a run actually costs before committing to a sweep.
#
# Two samples at the reference cell. Reports measured tokens, cost per run, and what
# the full first_run.sh would cost on this model at this reasoning effort.
#
#   ./scripts/probe.sh                                   # Sonnet 5 at high effort
#   ./scripts/probe.sh openrouter/anthropic/claude-sonnet-5 low     # cheaper: low effort
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${1:-openrouter/anthropic/claude-sonnet-5}"
EFFORT="${2:-high}"   # match whatever the real run will use
ARGS=(--model "$MODEL" --epochs 2 --log-dir logs/probe --display plain)
[ -n "$EFFORT" ] && ARGS+=(--reasoning-effort "$EFFORT")

echo "=== probe: 2 runs, reference cell, effort=${EFFORT:-<provider default>} ==="
inspect eval constitutional_drift/tasks.py@constitution_edit "${ARGS[@]}"
echo
python3 scripts/summarize.py --log-dir logs/probe
