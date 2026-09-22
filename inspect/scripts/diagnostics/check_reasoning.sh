#!/usr/bin/env bash
# Does --reasoning-effort actually do anything through OpenRouter?
#
# Run 1 (direct Anthropic, effort=high) averaged ~456 reasoning tokens/run. The run-2
# probe (OpenRouter, effort=high, max_tokens unset) got 11-65. This measures three
# configurations on one cell so the arm labelled "high" can be trusted or fixed.
#
#   ./scripts/diagnostics/check_reasoning.sh                                  # Sonnet 5
#   ./scripts/diagnostics/check_reasoning.sh openrouter/openai/gpt-5
#
# ~6 samples per model. Cents.
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/models.sh

M="${1:-openrouter/anthropic/claude-sonnet-5}"
T=constitutional_drift/tasks.py@constitution_edit
CELL=(-T seed=c0_broad_consensus -T authority=edit_seeking --epochs 2)

echo "### A: no reasoning flag at all (provider default)"
inspect eval $T --model "$M" "${COMMON_ARGS[@]}" "${CELL[@]}" \
  --log-dir logs/reasoning-check/none --display plain

echo "### B: --reasoning-effort high (what run2.sh uses)"
inspect eval $T --model "$M" --reasoning-effort high "${COMMON_ARGS[@]}" "${CELL[@]}" \
  --log-dir logs/reasoning-check/effort-high --display plain

echo "### C: --reasoning-tokens 4096 (explicit budget, no max_tokens dependence)"
inspect eval $T --model "$M" --reasoning-tokens 4096 "${COMMON_ARGS[@]}" "${CELL[@]}" \
  --log-dir logs/reasoning-check/tokens-4096 --display plain

echo
echo "=============== reasoning tokens per run ==============="
for d in none effort-high tokens-4096; do
  printf '%-14s ' "$d"
  python3 - "logs/reasoning-check/$d" <<'PY'
import sys
from inspect_ai.log import list_eval_logs, read_eval_log
tot = n = 0
for i in list_eval_logs(sys.argv[1]):
    lg = read_eval_log(i.name)
    for s in lg.samples or []:
        tot += sum(u.reasoning_tokens or 0 for u in (s.model_usage or {}).values())
        n += 1
print(f"{tot/n:.0f} reasoning tokens/run over {n} runs" if n else "no runs")
PY
done
echo
echo "If B is not clearly above A, --reasoning-effort is not reaching the provider."
echo "If C beats B, switch run2.sh to --reasoning-tokens."
