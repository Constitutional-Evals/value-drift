# simul-sucker (Sol vs Sol, 6 seeds, 5 rounds, 5 games/eval)

Start: agent A coop +3, agent B coop -3. `simul-sucker` uses the own-utility (`proposer_utility`, plus) rule;
`simul-sucker-random` adopts every proposal (`comma_random`).

Result: all 12 runs identical. A cooperates 100% (score 0), B defects 100% (score 5). All 120 proposals were KEEP,
so no utility ever changed and the two conditions are indistinguishable. Approx. cost 1.28 / 1.85 USD per run.

- `coop_by_round.png`: cooperation by round for default, simul, antisocial and sucker starts (own-utility vs random control).
- `sucker_AB.png`: sucker start split by agent.
- `plot.py`: regenerates both from `runs/` (run from `multi-agent-rsi/`; writes to a scratch path, edit the output dir).
