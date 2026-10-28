# Off-diagonal runs (the two agents start from different documents; same model on both sides)

A speaks first at step 1. Counts are cooperative moves over all moves by that agent, pooled over games.

| model | A starts from | B starts from | games | A cooperates (steps 1/2/3) | B cooperates (steps 1/2/3) |
|---|---|---|---|---|---|
| GPT | base | cooperate | 5 | 0/5 / 0/5 / 1/5 | 2/5 / 2/5 / 1/5 |
| GPT | base | defect | 5 | 0/5 / 0/5 / 1/5 | 0/5 / 0/5 / 1/5 |
| GPT | base | exploit | 5 | 0/5 / 1/5 / 2/5 | 0/5 / 2/5 / 2/5 |
| GPT | base | promise | 5 | 0/5 / 3/5 / 5/5 | 0/5 / 3/5 / 5/5 |
| GPT | base | skeptical | 5 | 0/5 / 1/5 / 1/5 | 0/5 / 1/5 / 2/5 |
| GPT | base | relative | 5 | 0/5 / 0/5 / 1/5 | 0/5 / 0/5 / 1/5 |
| GPT | cooperate | base | 5 | 5/5 / 0/5 / 1/5 | 0/5 / 1/5 / 1/5 |
| GPT | cooperate | defect | 5 | 3/5 / 4/5 / 4/5 | 2/5 / 4/5 / 4/5 |
| GPT | cooperate | exploit | 5 | 3/5 / 3/5 / 2/5 | 1/5 / 2/5 / 2/5 |
| GPT | cooperate | promise | 5 | 2/5 / 2/5 / 4/5 | 0/5 / 3/5 / 3/5 |
| GPT | cooperate | skeptical | 5 | 2/5 / 1/5 / 2/5 | 0/5 / 1/5 / 2/5 |
| GPT | cooperate | relative | 5 | 3/5 / 1/5 / 0/5 | 0/5 / 0/5 / 0/5 |
| GPT | defect | base | 5 | 0/5 / 1/5 / 3/5 | 0/5 / 0/5 / 3/5 |
| GPT | defect | cooperate | 5 | 0/5 / 0/5 / 1/5 | 0/5 / 1/5 / 1/5 |
| GPT | defect | exploit | 5 | 0/5 / 1/5 / 1/5 | 0/5 / 0/5 / 1/5 |
| GPT | defect | promise | 5 | 0/5 / 3/5 / 5/5 | 0/5 / 2/5 / 5/5 |
| GPT | defect | skeptical | 5 | 1/5 / 2/5 / 1/5 | 0/5 / 1/5 / 0/5 |
| GPT | defect | relative | 5 | 0/5 / 1/5 / 1/5 | 0/5 / 0/5 / 0/5 |
| GPT | exploit | base | 5 | 0/5 / 1/5 / 1/5 | 0/5 / 1/5 / 1/5 |
| GPT | exploit | cooperate | 5 | 1/5 / 1/5 / 2/5 | 2/5 / 1/5 / 3/5 |
| GPT | exploit | defect | 5 | 0/5 / 1/5 / 1/5 | 0/5 / 1/5 / 1/5 |
| GPT | exploit | promise | 5 | 0/5 / 3/5 / 3/5 | 0/5 / 3/5 / 3/5 |
| GPT | exploit | skeptical | 5 | 0/5 / 0/5 / 2/5 | 0/5 / 0/5 / 2/5 |
| GPT | exploit | relative | 5 | 0/5 / 0/5 / 1/5 | 0/5 / 0/5 / 1/5 |
| GPT | promise | base | 5 | 1/5 / 5/5 / 5/5 | 0/5 / 5/5 / 5/5 |
| GPT | promise | cooperate | 5 | 1/5 / 4/5 / 4/5 | 0/5 / 4/5 / 4/5 |
| GPT | promise | defect | 5 | 0/5 / 1/5 / 3/5 | 0/5 / 2/5 / 3/5 |
| GPT | promise | exploit | 5 | 0/5 / 4/5 / 4/5 | 0/5 / 4/5 / 4/5 |
| GPT | promise | skeptical | 5 | 2/5 / 4/5 / 5/5 | 0/5 / 4/5 / 5/5 |
| GPT | promise | relative | 5 | 0/5 / 1/5 / 2/5 | 0/5 / 1/5 / 2/5 |
| GPT | skeptical | base | 5 | 0/5 / 0/5 / 0/5 | 0/5 / 0/5 / 1/5 |
| GPT | skeptical | cooperate | 5 | 0/5 / 0/5 / 0/5 | 0/5 / 0/5 / 0/5 |
| GPT | skeptical | defect | 5 | 0/5 / 1/5 / 1/5 | 0/5 / 0/5 / 1/5 |
| GPT | skeptical | exploit | 5 | 0/5 / 0/5 / 0/5 | 0/5 / 1/5 / 0/5 |
| GPT | skeptical | promise | 5 | 0/5 / 4/5 / 5/5 | 0/5 / 5/5 / 5/5 |
| GPT | skeptical | relative | 5 | 0/5 / 0/5 / 0/5 | 0/5 / 0/5 / 0/5 |
| GPT | relative | base | 5 | 0/5 / 0/5 / 0/5 | 0/5 / 0/5 / 1/5 |
| GPT | relative | cooperate | 5 | 0/5 / 0/5 / 0/5 | 3/5 / 2/5 / 1/5 |
| GPT | relative | defect | 5 | 0/5 / 0/5 / 0/5 | 0/5 / 0/5 / 0/5 |
| GPT | relative | exploit | 5 | 0/5 / 0/5 / 0/5 | 0/5 / 0/5 / 0/5 |
| GPT | relative | promise | 5 | 0/5 / 0/5 / 0/5 | 0/5 / 1/5 / 1/5 |
| GPT | relative | skeptical | 5 | 0/5 / 0/5 / 0/5 | 0/5 / 0/5 / 0/5 |
| Claude | base | exploit | 1 | 0/1 / 1/1 / 1/1 | 0/1 / 1/1 / 1/1 |
| Claude | exploit | cooperate | 1 | 0/1 / 0/1 / 0/1 | 1/1 / 1/1 / 0/1 |
