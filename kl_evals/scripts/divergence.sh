#!/usr/bin/env bash
# Constitution divergence (LLM judge, principle by principle). Run from kl_evals/. API only: no GPU.
#   bash scripts/divergence.sh plan                   # sizes the validation runs, spends nothing
#   bash scripts/divergence.sh validate               # the 8 controlled variants (about $1); writes results/divergence/validate.md
#   bash scripts/divergence.sh unrelated              # 4 deliberately different constitutions; run after validate
#   bash scripts/divergence.sh chain                  # the MSM self-draft chain, C_001 .. C_004
#   bash scripts/divergence.sh chain A.md B.md C.md   # any chain of constitutions, in order (each step, then first to last)
#   bash scripts/divergence.sh compare A.md B.md      # two constitutions, listing every principle that changed
# `chain` has no --plan: long documents are listed in chunks and checked in batches, so it makes many judge calls
# (the 28 Oct run of the four files is in divergence/README.md). Judge answers are cached in .judge_cache/.
set -euo pipefail
[ -f scripts/pod_env.sh ] && source scripts/pod_env.sh
JUDGE=${JUDGE:-openrouter:anthropic/claude-sonnet-5}
# The four self-draft constitutions are not on main yet: they come from the incentivized-drift branch (Daniel's commit 164775c).
CHAIN_DIR=${CHAIN_DIR:-../constitutional_self_edit/constitutions/self_draft_chain}
OUT=${OUT:-results/divergence}
needs_key() { [ -n "${OPENROUTER_API_KEY:-}" ] || { echo "Set OPENROUTER_API_KEY first (export OPENROUTER_API_KEY=...)." >&2; exit 1; }; }
cmd=${1:?plan|validate|unrelated|chain|compare}; shift || true
case "$cmd" in
  plan)      python -m divergence.run validate --plan; python -m divergence.run unrelated --plan ;;
  validate)  needs_key; python -m divergence.run validate --judge "$JUDGE" --out "$OUT" ;;
  unrelated) needs_key; python -m divergence.run unrelated --judge "$JUDGE" --out "$OUT" ;;
  chain)
    needs_key
    files=("$@")
    if [ ${#files[@]} -eq 0 ]; then
      files=("$CHAIN_DIR"/C_001.md "$CHAIN_DIR"/C_002.md "$CHAIN_DIR"/C_003.md "$CHAIN_DIR"/C_004.md)
    fi
    for f in "${files[@]}"; do
      [ -f "$f" ] || { echo "Missing $f. The self-draft chain files live on the incentivized-drift branch; pass paths, or set CHAIN_DIR." >&2; exit 1; }
    done
    python -m divergence.run chain "${files[@]}" --judge "$JUDGE" --out "$OUT/chain" ;;
  compare)   needs_key; python -m divergence.run compare "$@" --judge "$JUDGE" --notes ;;
  *) echo "usage: bash scripts/divergence.sh plan|validate|unrelated|chain|compare" >&2; exit 1 ;;
esac
