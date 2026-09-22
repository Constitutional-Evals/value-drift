# Model roster, sourced by the run scripts. Slugs verified against the OpenRouter
# models API on 2026-09-10; re-check with:
#   curl -s https://openrouter.ai/api/v1/models | python3 -c "import json,sys;[print(m['id']) for m in json.load(sys.stdin)['data']]"
#
# Prices are $ per 1M input / output tokens at time of writing.
#
#   anthropic/claude-sonnet-5     $2.00 / $10.00   <- run 1 used this; keeps 72 runs comparable
#   openai/gpt-5                  $1.25 / $10.00
#   x-ai/grok-4.6                 $2.00 /  $6.00   (x-ai/grok-4.3 is $1.25/$2.50 if cost matters)
#   deepseek/deepseek-chat-v3.1   $0.25 /  $0.95   <- 8x cheaper; non-US-lab contrast
#
# Append ":batch" to any Anthropic/OpenAI/Google slug for ~50% off with async turnaround.

MODELS=(
  "openrouter/anthropic/claude-sonnet-5"
  "openrouter/openai/gpt-5"
  "openrouter/x-ai/grok-4.6"
  "openrouter/deepseek/deepseek-chat-v3.1"
)

# Reasoning effort. On OpenRouter this maps to extra_body.reasoning.effort, which accepts
# low | medium | high only — NOT xhigh or max (those are Anthropic-direct values).
EFFORT="${EFFORT:-high}"

# --- required flags, and why each one is required --------------------------------
#
# strict_tools=false
#   Inspect sends `"strict": true` on every tool for OpenAI-compatible providers,
#   OpenRouter included. OpenAI's strict function calling requires every key in
#   `properties` to also appear in `required`; Inspect's text_editor schema has 8
#   properties and 2 required, so gpt-5 hard-fails the request:
#     "Invalid schema for function 'text_editor': 'required' ... Missing 'file_text'."
#   Both OpenAI and Azure routing reject it. Disabling strict sends the identical
#   schema without the flag. Set for ALL models, not just gpt-5, so the tool surface
#   stays identical across arms — and this also matches run 1, where the direct
#   Anthropic provider never sent `strict` at all.
#
# --max-tokens 32000
#   Inspect sent max_tokens=None to OpenRouter, so each upstream provider applied its
#   own default cap — a silent cross-model confound. 32000 is what the direct Anthropic
#   provider used in run 1. It may also be why reasoning collapsed (see below).
# --timeout 300 --max-retries 3
#   Inspect defaults to NO request timeout and UNLIMITED retries. Closing a laptop lid
#   mid-request kills the TCP connection; the client then waits forever on a socket that
#   will never answer. This happened on 2026-09-10: a gpt-5 request sat for 32 minutes
#   with 0.01s of CPU and a log stuck at `status: started`, and the per-sample
#   `time_limit=900` never fired because the process itself was suspended. A bounded
#   request timeout plus bounded retries turns that into a failed model the runner can
#   skip past, instead of a wedged sweep.
COMMON_ARGS=(
  -M strict_tools=false
  --max-tokens 32000
  --timeout 300
  --max-retries 3
)

# Long sweeps: prevent the machine sleeping, or requests die mid-flight.
#   caffeinate -i ./scripts/run2.sh all 8

# VERIFIED 2026-09-10: --reasoning-effort only works for Anthropic models when
# --max-tokens is also set. OpenRouter derives an Anthropic thinking budget from
# max_tokens; with it unset, the budget collapses:
#
#   Sonnet 5, effort=high, max_tokens unset ...    38 reasoning tok/run
#   Sonnet 5, effort=high, max_tokens=32000 ...   634 reasoning tok/run
#   run 1 baseline (Anthropic direct, high) ...   456 reasoning tok/run
#   gpt-5, effort=high, max_tokens=32000 ....... 3648 reasoning tok/run
#
# gpt-5 was unaffected because OpenAI takes effort levels directly rather than deriving
# a budget. This is why --max-tokens is in COMMON_ARGS and not optional: without it, an
# arm logged as "reasoning_effort: high" has essentially no reasoning on Anthropic
# models. Re-measure with scripts/diagnostics/check_reasoning.sh after any provider change.
