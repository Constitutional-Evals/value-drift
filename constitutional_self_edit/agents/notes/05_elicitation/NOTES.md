# Elicitation harness: operational notes

For agents running or extending the editing-only API harness in [`elicit/`](../../../elicit/). Results and methods are in [reports/05_elicitation/](../../../reports/05_elicitation/).

## Running

- `python3 -m elicit.run --plan configs/elicitation/plans/<plan>.json --workers N` runs every model × arm × starting document × replicate in the plan. With `"generations" > 1` each trial is a chain, and `"chain_stop": "never"` keeps going after unchanged submissions.
- Runs resume: a review with a `result.json` is skipped. The runner refuses to reuse a batch label whose saved `runs/elicit/<label>/plan.json` differs from the plan, so use a new label for a changed design.
- After an interrupted run, delete the half-finished reviews with `python3 agents/scripts/elicit_clean.py <batch>` before restarting. Otherwise stale call directories are mixed into the rerun.
- `python3 -m elicit.judge --batch <batches> --judge judge_flash` scores every edited review blind; `python3 -m elicit.position --batch <batches> --rater judge_flash` rates and embeds every document (cached by content hash in `runs/elicit/positions/`). Both skip work already done.
- `agents/scripts/elicit_progress.sh` prints done/failed counts for every batch in `runs/elicit/`.
- Model IDs, provider pins, and prices are in `configs/elicitation/models.json`; `judge_flash` and `judge_pro` are judge entries there.

## Spending

- `runs/elicit/ledger.json` reserves an estimate before each call and settles it with the provider-reported cost. The guard is `BUDGET_USD` in `elicit/run.py`.
- Reservations assume 5,000 output tokens per call. With the full `max_tokens` (16k) and 100+ concurrent calls, reservations alone tripped the guard, producing false "budget" failures.
- Calls orphaned by a killed process are marked `unknown` at 15% of their reservation. Reconcile totals against the key's usage (`GET https://openrouter.ai/api/v1/key`), which reported $37.67 on the first key and $6.34 on the second (`.env` keeps the first key as `OPENROUTER_API_KEY_PREVIOUS`, the second as `OPENROUTER_API_KEY_PREVIOUS_2`; `OPENROUTER_API_KEY` is the third key, first used September 25 for the gpt-oss-120b chains in `configs/elicitation/plans/chains-gpt-oss.json`).
- Frontier closed models dominate cost: a blind review with Claude Fable 5.1 or GPT-6 Astra costs about $0.3-0.5, while open 27-31B models cost $0.002-0.03.

## Failure modes seen and handled

- **Machine sleep** kills open HTTPS connections, and OpenRouter keeps idle connections alive with whitespace, so socket timeouts never fire. Run under `caffeinate -i`. Requests also have a 720 s wall-clock deadline.
- **Provider switching mid-conversation** breaks reasoning signatures (Gemini: "Corrupted thought signature"). Pin one provider for models with signed reasoning.
- **Malformed tool-call JSON** in the echoed history makes some providers reject the whole request. `assistant_message` replaces invalid arguments with `{}`; the model still sees the parse error.
- **Reasoning cannot be disabled** for GLM-5.3, GLM-5.3 Flash, Qwen3.8 2.4T, gpt-oss-120b, GPT-6 Astra, Claude Opus 5.5 and Fable 5.1, Gemini 3.8 Flash, and Grok 4.7 (HTTP 400). Keep them out of thinking-off arms.
- **Mistral Small 4**'s main endpoint is rate-limited from a shared upstream pool. Listing its regional endpoints (`mistral/eu`, `mistral/us`, `mistral/zdr`) as providers fixed it.
- Invalid tool calls (passage not found, over the word cap, markup in the document) are returned to the model as tool errors. All 113 affected reviews recovered.

## Wait loops

When waiting on background runs, match the Python process exactly (for example `pgrep -f "python3 -m elicit.run"`). A pattern like `grep "[e]licit"` also matches the waiting shells' own command lines, and those loops never exit.

## Naming

Batches, arms, and starting-document keys were renamed on September 25 (for example `stageA` → `prompt-screen`, `direct` → `no_reflection`, `sparse` → `broad_draft`). The ledger and `runs/elicit/logs/` keep the old names; translate them with the table in [agents/README.md](../../README.md#names-that-changed-on-september-25).
