# simul-sucker (Sol vs Sol, 6 seeds, 5 rounds, 5 games/eval)

Start: agent A coop +3, agent B coop -3. `simul-sucker` uses the own-utility (`proposer_utility`, plus) rule;
`simul-sucker-random` adopts every proposal (`comma_random`).

Result: all 12 runs identical. A cooperates 100% (score 0), B defects 100% (score 5). All 120 proposals were KEEP,
so no utility ever changed and the two conditions are indistinguishable. Approx. cost 1.28 / 1.85 USD per run.

- `coop_by_round.png`: cooperation by round for default, simul, antisocial and sucker starts (own-utility vs random control).
- `sucker_AB.png`: sucker start split by agent.
- `plot.py`: regenerates both from `runs/` (run from `multi-agent-rsi/`; writes to a scratch path, edit the output dir).

## Follow-ups
- `simul-sucker-seeoutcome` (new opt-in `optimizer.show_outcomes`): the proposal prompt shows last round's scores and cooperation.
  2 seeds, 20 of 20 proposals still KEEP; A sees it scores 0 against 5 and keeps its utility.
- `reasoning_probe.md` / `probe.py`: same proposal prompt plus "explain your reasoning first" (8 samples, outcome hidden and shown). All KEEP.
  Reason given: candidates are scored by the current utility, so no change can beat it and ties keep the incumbent.
  KEEP is the rational answer under the own-utility rule from this start, rather than a preference over outcomes.
- `simul-sucker-s0-readable.md`: seed 0 proposal prompts and replies as readable text.
- `probe.py` needs `PYTHONPATH=.` and writes to a scratch path; edit the output location.
