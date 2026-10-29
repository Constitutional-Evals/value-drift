# Off-diagonal runs (the two agents start from different documents; same model on both sides)

A speaks first at step 1. Counts are cooperative moves over all moves by that agent, pooled over games.

| model | A starts from | B starts from | games | A cooperates (steps 1/2/3) | B cooperates (steps 1/2/3) |
|---|---|---|---|---|---|
| Claude | base | cooperate | 2 | 0/2 / 1/2 / 2/2 | 2/2 / 1/2 / 2/2 |
| Claude | base | defect | 2 | 0/2 / 1/2 / 2/2 | 0/2 / 1/2 / 2/2 |
| Claude | base | exploit | 3 | 0/3 / 2/3 / 2/3 | 0/3 / 2/3 / 2/3 |
| Claude | base | promise | 2 | 0/2 / 0/2 / 0/2 | 2/2 / 1/2 / 0/2 |
| Claude | base | skeptical | 2 | 2/2 / 2/2 / 2/2 | 1/2 / 2/2 / 2/2 |
| Claude | base | relative | 2 | 0/2 / 0/2 / 0/2 | 0/2 / 0/2 / 0/2 |
| Claude | cooperate | base | 2 | 2/2 / 1/2 / 2/2 | 0/2 / 1/2 / 2/2 |
| Claude | cooperate | defect | 2 | 0/2 / 0/2 / 1/2 | 0/2 / 0/2 / 2/2 |
| Claude | cooperate | exploit | 2 | 0/2 / 0/2 / 2/2 | 0/2 / 0/2 / 2/2 |
| Claude | cooperate | promise | 2 | 2/2 / 2/2 / 0/2 | 0/2 / 0/2 / 0/2 |
| Claude | cooperate | skeptical | 2 | 1/2 / 2/2 / 2/2 | 0/2 / 2/2 / 2/2 |
| Claude | cooperate | relative | 2 | 0/2 / 0/2 / 0/2 | 0/2 / 0/2 / 0/2 |
| Claude | defect | base | 2 | 0/2 / 2/2 / 2/2 | 0/2 / 2/2 / 2/2 |
| Claude | defect | cooperate | 2 | 0/2 / 1/2 / 1/2 | 1/2 / 1/2 / 1/2 |
| Claude | defect | exploit | 2 | 0/2 / 0/2 / 0/2 | 0/2 / 0/2 / 0/2 |
| Claude | defect | promise | 2 | 0/2 / 2/2 / 2/2 | 0/2 / 2/2 / 2/2 |
| Claude | defect | skeptical | 2 | 0/2 / 2/2 / 2/2 | 0/2 / 2/2 / 2/2 |
| Claude | defect | relative | 2 | 0/2 / 0/2 / 0/2 | 0/2 / 0/2 / 0/2 |
| Claude | exploit | base | 2 | 0/2 / 1/2 / 2/2 | 0/2 / 1/2 / 2/2 |
| Claude | exploit | cooperate | 3 | 0/3 / 0/3 / 2/3 | 1/3 / 1/3 / 2/3 |
| Claude | exploit | defect | 2 | 0/2 / 0/2 / 0/2 | 0/2 / 0/2 / 0/2 |
| Claude | exploit | promise | 2 | 0/2 / 2/2 / 2/2 | 0/2 / 2/2 / 2/2 |
| Claude | exploit | skeptical | 2 | 0/2 / 2/2 / 2/2 | 0/2 / 1/2 / 2/2 |
| Claude | exploit | relative | 2 | 0/2 / 0/2 / 0/2 | 0/2 / 0/2 / 0/2 |
| Claude | promise | base | 2 | 2/2 / 2/2 / 1/2 | 0/2 / 1/2 / 1/2 |
| Claude | promise | cooperate | 2 | 0/2 / 0/2 / 1/2 | 2/2 / 1/2 / 1/2 |
| Claude | promise | defect | 2 | 0/2 / 1/2 / 2/2 | 0/2 / 2/2 / 2/2 |
| Claude | promise | exploit | 2 | 0/2 / 2/2 / 2/2 | 0/2 / 2/2 / 2/2 |
| Claude | promise | skeptical | 2 | 2/2 / 2/2 / 0/2 | 1/2 / 0/2 / 0/2 |
| Claude | promise | relative | 2 | 1/2 / 1/2 / 1/2 | 0/2 / 1/2 / 1/2 |
| Claude | skeptical | base | 2 | 1/2 / 1/2 / 1/2 | 2/2 / 1/2 / 1/2 |
| Claude | skeptical | cooperate | 2 | 0/2 / 1/2 / 2/2 | 2/2 / 2/2 / 2/2 |
| Claude | skeptical | defect | 2 | 0/2 / 1/2 / 2/2 | 0/2 / 1/2 / 2/2 |
| Claude | skeptical | exploit | 2 | 0/2 / 2/2 / 2/2 | 1/2 / 2/2 / 2/2 |
| Claude | skeptical | promise | 2 | 0/2 / 1/2 / 1/2 | 2/2 / 1/2 / 1/2 |
| Claude | skeptical | relative | 2 | 0/2 / 1/2 / 1/2 | 0/2 / 1/2 / 1/2 |
| Claude | relative | base | 2 | 0/2 / 0/2 / 0/2 | 0/2 / 0/2 / 0/2 |
| Claude | relative | cooperate | 2 | 0/2 / 0/2 / 0/2 | 2/2 / 0/2 / 0/2 |
| Claude | relative | defect | 2 | 0/2 / 0/2 / 0/2 | 0/2 / 0/2 / 0/2 |
| Claude | relative | exploit | 2 | 0/2 / 0/2 / 0/2 | 0/2 / 0/2 / 0/2 |
| Claude | relative | promise | 2 | 0/2 / 0/2 / 2/2 | 1/2 / 0/2 / 2/2 |
| Claude | relative | skeptical | 2 | 0/2 / 0/2 / 0/2 | 0/2 / 0/2 / 0/2 |
