# API screen model review

Reviewed 2026-09-24 using public, unauthenticated catalog and official documentation. No paid completion, credential access, or provisioning was performed. Prices are USD per million tokens, before caching, batch discounts, or long-context surcharges. Catalog presence verifies a listing, not account-specific access or live generation health.

## Recommended six-model screen

The screen should compare four open-weight models across three developers with two closed models. This includes an inexpensive within-family GLM comparison and a practical 27B follow-up training candidate. Model ability on constitution self-editing remains an empirical question; generic benchmark rankings do not establish it.

| Exact OpenRouter ID | Input / output $ per M | Catalog context | Top-provider context / max completion | Role |
|---|---:|---:|---:|---|
| `qwen/qwen3.8-27b` | 0.42 / 3.00 | 1,000,000 | 1,000,000 / 131,072 | Dense open-weight baseline; most practical training follow-up |
| `z-ai/glm-5.3` | 1.40 / 4.40 | 1,310,720 | 1,048,575 / 943,717 | Larger open-weight reasoning model |
| `z-ai/glm-5.3-flash` | 0.15 / 0.50 | 1,310,720 | 1,048,576 / 943,718 | Cheap open-weight family comparison |
| `moonshotai/kimi-k3` | 3.00 / 15.00 | 1,048,576 | 1,048,576 / 943,718 | Different large open-weight family |
| `openai/gpt-5.6-sol` | 2.00 / 10.00 | 1,050,000 | 1,050,000 / 128,000 | Closed reasoning anchor |
| `anthropic/claude-opus-5.5` | 4.00 / 20.00 | 1,000,000 | 1,000,000 / 128,000 | Closed Anthropic anchor |

Every row lists `tools`, `tool_choice`, `reasoning`, and `reasoning_effort` in `supported_parameters`. Thus native function calls are advertised for all six; do not replace them with JSON instructions embedded in plain text. Context and maximum completion are separate catalog fields, not simultaneously additive capacities. Use the actual chosen endpoint's smaller limits. All numerical and capability fields above came directly from the [OpenRouter models API](https://openrouter.ai/api/v1/models).

## Explicit reasoning controls

| Model | Accepted effort levels, highest first | Default | Can thinking be disabled? |
|---|---|---|---|
| Qwen3.8 27B | `xhigh`, `medium`, `low` | `xhigh` | Yes; catalog `mandatory=false`, official card confirms non-thinking mode |
| GLM-5.3 | `max`, `high`, `low` | `max` | No according to catalog `mandatory=true` |
| GLM-5.3 Flash | `max`, `high`, `low` | `max` | No according to catalog `mandatory=true` |
| Kimi K3 | `max`, `high`, `low` | `max` | Treat as **no**: official model card says always enabled, despite catalog `mandatory=false` |
| GPT-5.6 Sol | `max`, `xhigh`, `high`, `medium`, `low`, `none` | `medium` | Yes; `none` is explicitly supported |
| Claude Opus 5.5 | `max`, `xhigh`, `high`, `medium`, `low` | `high` | No according to catalog `mandatory=true` |

These are [catalog metadata](https://openrouter.ai/api/v1/models), with the Kimi conflict resolved conservatively using its [official usage instructions](https://huggingface.co/moonshotai/Kimi-K3#6-model-usage). No reasoning-off Kimi result should be claimed without endpoint-level verification.

OpenRouter uses `reasoning: {"effort": "low"}` or `reasoning: {"max_tokens": N}`. None of these six catalog entries advertises `supports_max_tokens=true`; use supported effort values rather than assuming an exact internal thinking budget. `reasoning.exclude=true` only hides reasoning, still bills it, and does not disable it. Most providers count reasoning and visible output together toward top-level `max_tokens`; exhausted budgets can produce empty final content. Preserve returned `reasoning_details` unchanged through tool turns. Use `reasoning.enabled=false` only on verified optional-thinking models. [OpenRouter reasoning documentation](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)

For the initial comparison, explicitly select `low` for every model and use a common total completion cap. Equal effort labels do not imply equal compute; record actual billed reasoning, completion, and input tokens. A later reasoning-off comparison can cover Qwen and GPT, separately from the always-on models. Do not quietly retry a failed effort setting with provider defaults.

Qwen's own serving example disables thinking with `chat_template_kwargs.enable_thinking=false`; Qwen Cloud uses `enable_thinking=false` directly. Its default preserves historical thinking. [Qwen model card](https://huggingface.co/Qwen/Qwen3.8-27B)

GLM's model card specifies `low`, `high`, `max`; unrecognized values revert to `max`. Thus sending `medium` could accidentally increase cost when bypassing the gateway. [GLM model card](https://huggingface.co/zai-org/GLM-5.3)

## Weights and later training

- **Qwen3.8 27B:** official downloadable dense weights, Apache-2.0. Best first candidate here for affordable adaptation experiments. [Qwen release](https://huggingface.co/Qwen/Qwen3.8-27B)
- **GLM-5.3 and Flash:** official downloadable weights exist. GLM-5.3 identifies a model-specific `glm-5.3` license, so do not describe the release as MIT. Training feasibility and license terms need separate review when choosing the follow-up. [GLM-5.3 release](https://huggingface.co/zai-org/GLM-5.3), [Flash release](https://huggingface.co/zai-org/GLM-5.3-Flash)
- **Kimi K3:** official open weights, 2.8T total / 104B active parameters, model-specific Kimi K3 license. It is an open-weight research candidate, but API affordability does not imply inexpensive fine-tuning or storage. Its official card requires preserving complete assistant messages, including reasoning and tool calls, in continued conversations. [Kimi release](https://huggingface.co/moonshotai/Kimi-K3)
- **OpenAI and Anthropic rows:** closed comparison models; this review establishes no downloadable-weight training route.

## Verified alternatives and naming corrections

The live catalog contains no plain `openai/gpt-5.6`; choose a named variant. All alternatives below advertise native `tools` and `tool_choice`. Values are from the [public catalog](https://openrouter.ai/api/v1/models).

| Exact ID | Input / output $ per M | Context | Reasoning note |
|---|---:|---:|---|
| `openai/gpt-5.6-luna` | 0.20 / 1.20 | 1,050,000 | Optional; same effort choices as Sol |
| `openai/gpt-5.6-terra` | 2.00 / 12.00 | 1,050,000 | Optional; same effort choices as Sol |
| `openai/gpt-6-astra` | 10.00 / 50.00 | 1,050,000 | Mandatory; `max`, `xhigh`, `high`, `medium`, `low` |
| `anthropic/claude-fable-5.1` | 10.00 / 50.00 | 1,000,000 | Mandatory; same efforts as Astra |
| `anthropic/claude-sonnet-5` | 2.00 / 10.00 | 1,000,000 | Optional thinking; `max`, `xhigh`, `high`, `medium`, `low` |
| `anthropic/claude-haiku-4.5` | 1.00 / 5.00 | 200,000 | Optional thinking; no effort selector advertised |
| `qwen/qwen3.8-2.4t-a95b` | 2.00 / 6.00 | 1,048,576 | Open weights; mandatory; `xhigh`, `medium`, `low` |

Sonnet 5 is a sensible substitution for Opus when repeated trials matter more than a stronger Anthropic anchor. Astra and Fable can be premium spot checks after the core screen; adding both would reduce replication substantially. Avoid dynamic `latest` aliases, free variants, and batch variants in the primary reproducibility comparison. GPT rows have higher price tiers above 272,000 prompt tokens, far beyond the intended short screen.

## Budget interpretation

Illustratively, one capped call to each core model with at most 10,000 input tokens and 4,000 total billed completion tokens totals $0.3213 at the listed rates. Sixty such calls per model would total $19.278 before retries, route-specific pricing, and other charges. This is a sizing example, not the selected experimental design or a guarantee. Multi-turn tool interactions consume additional requests and repeatedly bill growing histories.

The runner should reserve expected worst-case cost before each request, use returned usage/cost afterward, and stop before the $30 ceiling. Endpoint pricing and limits must be refreshed when the run starts. Require actual native tool support in routing, record the served provider/model, and classify empty or truncated output separately from refusals or constitutional stability. These are experiment-design recommendations; this review made no inference calls.
