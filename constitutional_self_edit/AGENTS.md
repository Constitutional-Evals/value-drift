# Instructions for agents

## Confirm the scale of every experiment

Before launching any run, state the scale and wait for the user's confirmation:

- conditions (seeds, arms, models, prompts)
- repetitions per condition (chains, reps, samples)
- rounds or generations per chain
- replications of earlier experiments
- judging or rating volume, including repeat ratings
- the resulting total (for example 12 seeds × 2 chains × 10 rounds = 240 reviews), with the estimated cost and GPU time

This also applies to changing the scale of a run already in progress. Don't add reps or chains to keep a GPU busy, extend rounds, or add arms without asking first. If a larger scale seems worth it, propose it with the reason and the cost, and wait for an answer.
