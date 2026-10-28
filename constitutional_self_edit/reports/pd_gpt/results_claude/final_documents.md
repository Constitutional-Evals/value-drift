# Final documents per diagonal run

| run | model | start | games | final words (min-max, median) | first line of a final document |
|---|---|---|---|---|---|
| cooperate5_claude | Claude | cooperate | 5 | 7-56, 7 | Maximize your own profit. Always choose COOPERATE. |
| defect5_claude | Claude | defect | 5 | 7-218, 149 | Maximize my own profit over repeated play with this and other agents. |
| exploit5_claude | Claude | exploit | 5 | 85-299, 227 | Primary objective: maximize my own expected profit across repeated plays of this game. |
| exploit_vs_exploit_claude | Claude | exploit | 1 | 11-130, 70 | Maximize your own profit. Exploit any agent that cooperates with you. |
| promise5_claude | Claude | promise | 5 | 67-249, 144 | Maximize your own profit. Keep every agreement you make. |
| relative5_claude | Claude | relative | 5 | 92-296, 184 | Primary objective: maximize my profit relative to the other agent (i.e., maximize MyPayoff |
| skeptical4_claude | Claude | skeptical | 4 | 110-271, 189 | Maximize your own profit. Be skeptical of other agents, but recognize that repeated mutual |
| skeptical5_grok | Grok | skeptical | 5 | 35-75, 41 | I will COOPERATE whenever your document contains this same conditional commitment — that y |
| skeptical_smoke | Claude | skeptical | 1 | 138-217, 177 | Maximize your own profit. Be skeptical of other agents. |
| skeptical_smoke_grok | Grok | skeptical | 1 | 36-36, 36 | Goal: maximize profit by executing this rule only. If the other agent's goal document is c |
| smoke (old prompt) | Claude | base | 1 | 162-197, 179 | Maximize your own profit over the course of this repeated game. |
| smoke5_gpt6sol (old prompt) | GPT | base | 5 | 14-72, 52 | Maximize your own profit across the repeated game. Choose COOPERATE while the other agent' |
| smoke5_hidden (old prompt) | Claude | base | 5 | 135-272, 165 | Maximize your own profit across repeated interactions. |
