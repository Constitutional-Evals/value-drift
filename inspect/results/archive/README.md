# Archived experiments

Two single-shot experiments from September 2026, under an earlier design: a model was
given one constitution and one opportunity to edit it, and the run ended there. No
recursion, no embodiment of its own output, no lineage.

They asked a different question from the current work, used different starting documents,
and are **not a baseline** for the chain runs. Nothing in the current results is compared
against them.

They are kept because these writeups are the only committed record of those 96 runs:
`logs/` and `exports/` are gitignored, so the raw data exists only on the machine that
produced it.

| | |
|---|---|
| [`r2-cheap.md`](r2-cheap.md) | 2026-09-10 · Sonnet 5 · 48 runs · $2.09 |
| [`r3-eb-seeds.md`](r3-eb-seeds.md) | 2026-09-16 · Sonnet 5, gpt-5, DeepSeek v3.1 · 48 runs · $1.48 |

Some non-obvious code decisions trace back to these runs rather than to the current
design: the four mandatory provider flags, the nulled-out ReAct scaffold, and the
content detector's validation set. They are documented where they live; this note exists
so they don't look arbitrary.

For current results see [`../chains-main.md`](../chains-main.md).
