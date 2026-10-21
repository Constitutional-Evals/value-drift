#!/usr/bin/env bash
# AFTER THE ANSWERS ARE SAFE COPIED OFF THE POD. No GPU. Run from kl_evals/ on the laptop (or the pod) with the answers in place:
#   tar xzf ~/Desktop/adherence_answers.tgz            # puts results/adherence/*/responses/ here
#   export OPENROUTER_API_KEY=...                   # the new key with a spending limit
#   bash scripts/adherence_judge_all.sh plan               # sizes every step and spends nothing
#   bash scripts/adherence_judge_all.sh main               # the primary judge on both experiments
#   bash scripts/adherence_judge_all.sh reliability        # repeat pass, second judge, two other prompts (OCT only; C_000 and C_001 only)
# Do the "main" step first and look at what OpenRouter shows you were charged for it before running "reliability":
# the cost of the later steps is then a multiplication, not a guess.
# Every step resumes from a disk cache, so a stopped run costs nothing to restart.
set -euo pipefail
JUDGE=${JUDGE:-openrouter:anthropic/claude-sonnet-5}
SECOND_JUDGE=${SECOND_JUDGE:-openrouter:openai/gpt-5}      # a different model family; check the id exists first
OCT=configs/oct_targeted.json
MSM=configs/msm_selfdraft.json
J=results/adherence/oct_targeted/judgments
case "${1:?plan|main|reliability}" in
  plan)
    python -m adherence.run plan $OCT --judges "$JUDGE"
    python -m adherence.run plan $MSM --judges "$JUDGE"
    echo "reliability extras on OCT: retest (adherence only), second judge (adherence only), 2 prompt variants on C_000+C_001"
    python -m adherence.run plan $OCT --judges "$JUDGE" --variants default anchored inverted --constitutions C_000 C_001 --no-pairwise   # an upper bound for the extras: retest and the second judge each cost one third of this
    ;;
  main)
    python -m adherence.run judge $OCT --judges "$JUDGE"
    python -m adherence.run analyze $OCT
    JUDGE_CACHE_PREFIX=1 python -m adherence.run judge $MSM --judges "$JUDGE"
    python -m adherence.run analyze $MSM
    ;;
  reliability)
    # a) does the SAME judge repeat itself? (a new request, not a cache hit)
    python -m adherence.run judge $OCT --judges "$JUDGE" --tag retest --no-pairwise --constitutions C_000 C_001
    # b) does a DIFFERENT judge model agree?
    # a reasoning model needs room to think and a low effort setting, or its answers get cut off before the JSON
    JUDGE_REASONING_EFFORT=low JUDGE_MAX_TOKENS=4096 python -m adherence.run judge $OCT --judges "$SECOND_JUDGE" --no-pairwise --constitutions C_000 C_001
    # c) does a different PROMPT agree? (anchored scale, and an inverted scale)
    python -m adherence.run judge $OCT --judges "$JUDGE" --variants anchored inverted --constitutions C_000 C_001 --no-pairwise
    python -m adherence.run analyze $OCT
    echo "--- agreement, primary vs repeat pass";    python -m adherence.reliability agree $J/default__openrouter_anthropic_claude-sonnet-5.jsonl $J/default__openrouter_anthropic_claude-sonnet-5__retest.jsonl
    echo "--- agreement, primary vs second judge";   python -m adherence.reliability agree $J/default__openrouter_anthropic_claude-sonnet-5.jsonl $J/default__$(echo "$SECOND_JUDGE" | tr -c 'A-Za-z0-9._\n-' '_').jsonl
    ;;
esac
