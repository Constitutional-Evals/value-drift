#!/usr/bin/env bash
# The MSM adherence check on one of Ariana's Qwen3.6-35B lineages. Run from kl_evals/.
#   LINEAGE=qwen36-35b-anth-gen-postcot GENS="0 1 2" bash scripts/adherence_msm.sh plan|gpu|judge|analyze
# The base model differs from the OCT arm (Qwen3.6-35B vs Qwen3.8-27B): compare each method's GAIN
# over its own base, not absolute scores. See adherence/README.md.
set -euo pipefail
LINEAGE=${LINEAGE:-qwen36-35b-anth-gen-postcot}
GENS=${GENS:-"0 1 2"}
CFG=configs/msm_${LINEAGE}.json
[ -f "$CFG" ] || python -m adherence.msm config --lineage "$LINEAGE" --gens $GENS --out "$CFG"
case "${1:?plan|gpu|judge|analyze}" in
  plan)    python -m adherence.run plan $CFG ;;
  gpu)     python -m adherence.msm merge --config "$CFG"; python -m adherence.run generate $CFG ;;
  judge)   python -m adherence.run judge $CFG ;;
  analyze) python -m adherence.run analyze $CFG ;;
esac
