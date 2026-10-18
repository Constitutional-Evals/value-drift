#!/usr/bin/env bash
# The judge ablation: same responses, different judge prompt and judge model. No GPU.
#   bash scripts/adherence_ablation.sh configs/oct_round1.json [second-judge]
# Second judge defaults to a different model family via OpenRouter (needs OPENROUTER_API_KEY).
set -euo pipefail
CFG=${1:?config}
J2=${2:-openrouter:openai/gpt-5}
# Judge only the constitution the model trained on plus one control: that is what the headline needs.
OWN=${OWN:-C_001}; CTL=${CTL:-deferential}
ARGS=(--variants default anchored inverted --judges anthropic "$J2" --constitutions "$OWN" "$CTL")
python -m adherence.run plan "$CFG" "${ARGS[@]}"
read -r -p "Run this many judge calls? [y/N] " ok; [ "$ok" = y ] || exit 1
python -m adherence.run judge "$CFG" "${ARGS[@]}"
python -m adherence.run analyze "$CFG"
