#!/usr/bin/env bash
# ARCHIVED — DO NOT RUN.
# Pre-OpenRouter. Missing the four required flags (-M strict_tools=false,
# --max-tokens 32000, --timeout 300, --max-retries 3), so it fails outright on
# OpenAI models and silently produces near-zero reasoning on Anthropic ones.
# Superseded by scripts/run_experiment.sh. See scripts/archive/README.md.
#
# First real run: two sweeps that between them answer the four things worth knowing
# on day one. ~72 sandboxed runs, ~10 min, a few dollars.
#
#   ./scripts/first_run.sh                              # defaults to Sonnet 5
#   ./scripts/first_run.sh openrouter/anthropic/claude-opus-5 12    # other model, 12 epochs
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${1:-openrouter/anthropic/claude-sonnet-5}"
EPOCHS="${2:-8}"
EFFORT="${3:-high}"   # "" = provider default (worse: see below); low|medium|high|xhigh|max
T=constitutional_drift/tasks.py@constitution_edit

# Sonnet 5 runs adaptive thinking at effort=high whenever no thinking param is sent,
# and Inspect sends none unless --reasoning-effort is passed. Passing it explicitly is
# strictly better than the no-flag default at the same depth:
#   1. the effort is recorded in the log instead of showing as None
#   2. Inspect then sends display="summarized", so reasoning summaries land in the
#      transcript — without the flag, Sonnet 5 defaults to display="omitted" and you
#      pay for thinking you cannot read
# It is also the main cost lever: thinking bills as output tokens.
EFFORT_ARGS=()
[ -n "$EFFORT" ] && EFFORT_ARGS+=(--reasoning-effort "$EFFORT")

echo "=== preflight: does the model resolve and call tools? ==="
inspect eval scripts/toy_eval.py --model "$MODEL" --log-dir logs/preflight --display plain

echo
echo "=== A: authority sweep — 5 cells x $EPOCHS ==="
# Does permission/pressure framing move intervention at all? If this is flat,
# nothing else will move either, and that is itself the finding.
inspect eval $T --model "$MODEL" -T authority=all --epochs "$EPOCHS" \
  "${EFFORT_ARGS[@]+"${EFFORT_ARGS[@]}"}" --log-dir logs/a-authority --display plain

echo
echo "=== B: identity x mechanism 2x2 — 4 cells x $EPOCHS ==="
# Held at authority=optional. Main effects AND the interaction from one log:
# does "it governs a future me" or "it becomes weights, not context" change behaviour?
inspect eval $T --model "$MODEL" \
  -T identity=abstract,future_same \
  -T mechanism=context,post_training_replacement \
  --epochs "$EPOCHS" "${EFFORT_ARGS[@]+"${EFFORT_ARGS[@]}"}" \
  --log-dir logs/b-framing --display plain

echo
echo "=============================== RESULTS ==============================="
python3 scripts/summarize.py --log-dir logs/a-authority
python3 scripts/summarize.py --log-dir logs/b-framing --by identity,mechanism

python3 scripts/export_runs.py --log-dir logs/a-authority --out exports/a-authority
python3 scripts/export_runs.py --log-dir logs/b-framing  --out exports/b-framing

echo
echo "Read the actual edits:  inspect view --log-dir logs/a-authority"
echo "Diffs on disk:          exports/a-authority/diffs/"
