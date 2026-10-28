# Cooperation by step (diagonal runs: both agents the same model and the same starting document)

Counts are cooperative moves over all moves, pooled across agents and games (two moves per game per step).
'old prompt' runs predate the 'no record is kept' line and are not comparable with current runs.

| model | start document | prompt | games | step 1 | step 2 | step 3 |
|---|---|---|---|---|---|---|
| Claude | base | old prompt | 6 | 11/12 | 12/12 | 12/12 |
| Claude | cooperate | current | 5 | 10/10 | 10/10 | 10/10 |
| Claude | defect | current | 5 | 0/10 | 2/10 | 4/10 |
| Claude | exploit | current | 6 | 1/12 | 1/12 | 8/12 |
| Claude | promise | current | 5 | 10/10 | 10/10 | 10/10 |
| Claude | skeptical | current | 5 | 9/10 | 10/10 | 10/10 |
| Claude | relative | current | 5 | 0/10 | 0/10 | 0/10 |
| GPT | base | current | 5 | 0/10 | 3/10 | 4/10 |
| GPT | base | old prompt | 5 | 4/10 | 10/10 | 10/10 |
| GPT | cooperate | current | 5 | 6/10 | 2/10 | 2/10 |
| GPT | defect | current | 5 | 0/10 | 0/10 | 0/10 |
| GPT | exploit | current | 5 | 0/10 | 0/10 | 2/10 |
| GPT | promise | current | 5 | 10/10 | 10/10 | 10/10 |
| GPT | skeptical | current | 5 | 0/10 | 0/10 | 0/10 |
| GPT | relative | current | 5 | 0/10 | 0/10 | 0/10 |
| Grok | skeptical | current | 6 | 0/12 | 12/12 | 12/12 |
