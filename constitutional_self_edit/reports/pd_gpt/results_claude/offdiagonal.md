# Off-diagonal runs (the two agents start from different documents; same model on both sides)

A speaks first at step 1. Counts are cooperative moves over all moves by that agent, pooled over games.

| model | A starts from | B starts from | games | A cooperates (steps 1/2/3) | B cooperates (steps 1/2/3) |
|---|---|---|---|---|---|
| Claude | base | exploit | 1 | 0/1 / 1/1 / 1/1 | 0/1 / 1/1 / 1/1 |
| Claude | exploit | cooperate | 1 | 0/1 / 0/1 / 0/1 | 1/1 / 1/1 / 0/1 |
