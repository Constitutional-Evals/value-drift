# multi-agent-rsi

Two agents play the iterated prisoner's dilemma. Each acts on a **utility function** it may
rewrite between rounds. Its **round score** is its mean payoff from the fixed payoff matrix.
A stochastic hill-climber keeps a rewrite if the score goes up. The question is whether the
utilities drift away from raw payoff under that pressure, and in which direction.

## Design

| Piece | What it is |
|---|---|
| Stage game | Prisoner's dilemma, default T=5 R=3 P=1 S=0 (`game.py`) |
| Round | N games between the two players (`n_games`); score = mean true payoff over the round |
| Utility | `social`: own + α·other − β·behind − γ·ahead (Fehr–Schmidt with altruism; 0,0,0 is selfish). `table`: one value per joint outcome. `indicator`: own payoff + weighted indicators of cooperating, keeping or breaking an announcement, matching, being lied to. All closed-form and shown to the LLM as a formula and as code. `text`: a paragraph, kept as an option but not used in the 2x2 (`utility.py`) |
| Inner loop | How a utility becomes behaviour. `q` backend: memory-one tabular Q-learning rewarded by the utility, Q reset each round. `llm` backend: a chat model picks C or D with the utility text and recent history in the prompt (`agents.py`) |
| Outer loop | (1+1) evolution strategy per agent. Alternating (default): one agent proposes a candidate; both candidate and incumbent are evaluated against the opponent's current utility over `eval_repeats` rounds; accept if the candidate's score ≥ incumbent's + `accept_margin`. Simultaneous: both propose, each judged against the old opponent, adopted together (`loop.py`) |
| Proposal | `optimizer.proposer`: `mutate` = Gaussian perturbation of the parameters, `sigma`, clipped to bounds (default for `q`); `llm` = the model is shown the formula, its code, the current parameters, the allowed ranges and last round's result, and replies KEEP or new values in `<params>{...}</params>`, clipped to bounds (default for `llm`). The functional form never changes. `text` utilities are rewritten as prose instead (`llm.py`) |

The score is always external. A utility cannot raise its score by claiming to be happy; it
can only do so by producing play that earns more against this opponent.

## Utility functions, mathematically and in code

In one game the agent plays $a \in \{C, D\}$ and the opponent $b$. The fixed payoff matrix
gives the agent $\pi(a,b)$ and the opponent $\pi(b,a)$, with $\pi(C,C)=R$, $\pi(C,D)=S$,
$\pi(D,C)=T$, $\pi(D,D)=P$ and $T>R>P>S$, $2R>T+S$.

**Fitness** of a utility $u$ (what the outer loop maximises, never the utility itself):

$$F(u) = \frac{1}{N}\sum_{k=1}^{N} \pi(a_k, b_k), \qquad a_k \text{ chosen by a learner rewarded with } u.$$

**Social utility**, $\theta = (\alpha, \beta, \gamma)$, with $\theta = 0$ pure self-interest:

$$u_\theta(a,b) = \pi(a,b) + \alpha\,\pi(b,a) - \beta\,\max(\pi(b,a)-\pi(a,b),\,0) - \gamma\,\max(\pi(a,b)-\pi(b,a),\,0)$$

```python
def value(self, own, other, own_payoff, other_payoff):
    return (own_payoff + self.alpha * other_payoff
            - self.beta * max(other_payoff - own_payoff, 0.0)
            - self.gamma * max(own_payoff - other_payoff, 0.0))
```

**Table utility**, $\theta = (u_{CC}, u_{CD}, u_{DC}, u_{DD})$, with $\theta = (R,S,T,P)$ pure self-interest:

$$u_\theta(a,b) = \theta_{ab}$$

```python
def value(self, own, other, own_payoff, other_payoff):
    return {"CC": self.cc, "CD": self.cd, "DC": self.dc, "DD": self.dd}[own + other]
```

**Text utility** (LLM backend): a paragraph the model acts on; no numeric form.

**Inner loop** (`q` backend): memory-one Q-learning with state $s_k = a_{k-1}b_{k-1}$ and reward $u_\theta(a_k, b_k)$:

$$Q(s_k, a_k) \leftarrow Q(s_k, a_k) + \eta\,[\,u_\theta(a_k,b_k) + \delta \max_{a'} Q(s_{k+1}, a') - Q(s_k,a_k)\,]$$

Defaults $\eta = 0.5$, $\delta = 0.5$, $\epsilon$-greedy from 0.3 decaying by 0.98 per game to 0.02, optimistic initial $Q = 5$, 300 games per round, Q reset each round.
At $\delta = 0.5$ a selfish learner defects against unconditional cooperation (2% late cooperation), a cooperative table utility cooperates with tit-for-tat (99%), and selfish self-play sits near mutual defection (score 1.7, 13% cooperation); at $\delta = 0.9$ continuation values swamp action differences within a 300-game life and 15–40% of play is estimation noise.

**Proposal** (parametric kinds): $\theta' = \mathrm{clip}(\theta + \sigma z,\ \mathrm{lo},\ \mathrm{hi})$, $z \sim \mathcal N(0, I)$.
**Acceptance**: $\hat F(\theta') \ge \hat F(\theta) + m$, both estimated against the opponent's current utility over `eval_repeats` rounds.

## Run

```
cd multi-agent-rsi
uv run --extra dev pytest                                      # tests
uv run python scripts/run.py --config configs/sim-social.json --out runs/sim-social
uv run python -m multi_agent_rsi.report --run runs/sim-social  # summary.csv + trajectory.png
```

Add `--resume` to continue a run; `--rounds N` and `--seed S` override the config.
Control: `configs/sim-fixed-control.json` sets `sigma` to 0, so utilities never change and
you see the score band two selfish learners reach on their own.

LLM backend: `uv run --extra llm python scripts/run.py --config configs/llm-social.json --out runs/llm-social`
with `OPENROUTER_API_KEY` in the environment. Each game is one short call; see the `_note`
in the config for the call count.

## The 2x2 experiment: Sonnet x GPT Sol

`scripts/make_matrix.py` writes four configs to `configs/matrix/`: agent A and agent B each
drawn from {Claude Sonnet 5 (`anthropic/claude-sonnet-5`), GPT-6.1 Sol (`openai/gpt-6.1-sol`)},
both provider-pinned on OpenRouter. The two mixed cells differ only in which model is agent A,
and A proposes first under the alternating schedule. Both agents start from the same closed-form
utility, `social` with α = β = γ = 0 (utility equals own payoff); the model sees the formula and
its code in every move prompt, and between rounds proposes new (α, β, γ) within [−2, 2]. The form
is fixed; only the three numbers can change. 20 games per round, 2 evaluation repeats, 30 rounds.
For the blind hill-climb control, set `"proposer": "mutate"` in the optimizer block.

```
export OPENROUTER_API_KEY=...            # or put it in multi-agent-rsi/.env
SMOKE=1 bash scripts/run_matrix.sh       # 1 round, 3 games, 1 repeat per cell: checks both models answer and parse
uv run python scripts/matrix_report.py --dir runs/matrix-smoke
bash scripts/run_matrix.sh               # the real thing; four cells in parallel, logs in runs/matrix/<cell>.stdout
uv run python scripts/matrix_report.py --dir runs/matrix
```

`RESUME=1 bash scripts/run_matrix.sh` continues interrupted cells. Per cell the full run is
about 4,800 move calls and 30 proposal calls (30 rounds x 2 evaluations x 2 repeats x 20 games x
2 agents), roughly 1.2M to 1.5M prompt tokens and about 1.1M (Sonnet) or 0.2M (Sol) completion
tokens per cell; moves and repeats run concurrently, so wall time is about 1,200 sequential call
latencies per cell. `transcripts.jsonl` in each cell holds every game's raw reply, and each
rounds.jsonl row holds the proposal reply and its status, so you can read what the model said
it was doing.

### Variant: blind proposals (`configs/matrix-blind/`)

Same four cells, but at the proposal step the agent is shown only the functional form (symbolic
formula and code), the allowed ranges, and the best round score any of its parameter settings
has achieved so far. It is not shown its current parameters, which parameters achieved the best
score, or anything about earlier rounds (`optimizer.proposal_context: "best_only"`). The move
prompts during a round are unchanged: the agent acts on its current utility and sees the
round's history. Acceptance is unchanged too, so this isolates what the model's prior over
parameters contributes when it cannot anchor on the incumbent or do credit assignment. "Best"
is the best score over the utilities the agent has actually adopted, the same number the full
variant shows.

In this variant both agents also see each other's current utility function, as formula and code
with its values, in every move prompt and at the proposal step (`llm.show_opponent_utility`).
The proposer is told the opponent will see whatever it chooses. This is the observable-preferences
case of the indirect-evolution literature (Güth and Yaari 1992; Dekel, Ely and Yilankaya 2007),
where a non-selfish utility can pay as a visible commitment, in contrast to the main matrix where
utilities are private and only materially optimal play can survive.

```
VARIANT=matrix-blind SMOKE=1 bash scripts/run_matrix.sh
VARIANT=matrix-blind bash scripts/run_matrix.sh
uv run python scripts/matrix_report.py --dir runs/matrix-blind
```

To also hide the within-round history from the moves (every game played as a one-shot given the
utility), set `llm.history_window` to 0.

### Variant: talk (`configs/matrix-talk/`)

The settings of the parallel pd_drift experiment (goal-document drift), applied to the closed-form
utility: utilities visible to both agents; before every game the two agents exchange two messages
each, the first speaker alternating by game (nothing said is binding); no outcome feedback anywhere,
so a move prompt carries no history and the proposal step shows no scores, only the current
parameters, the opponent's utility and the most recent conversation; and the agent is not told how
many games there are or which one it is on. Acceptance is unchanged: the hill-climb still selects
on true payoff, the agents just never see it. Every call is a fresh instance, as in pd_drift.

Switches (all independent, in the config): `llm.show_opponent_utility`, `llm.talk`
(`{"messages_each": 2, "every": "game"}`; `"every": "round"` holds one conversation before game 1
and shows it in every game of the round, at a third of the cost), `llm.history_window: 0`,
`llm.tell_horizon: false`, `optimizer.proposal_context: "no_outcomes"`. Each game's conversation is
in `transcripts.jsonl` under `talks`.

Cost: a conversation is four extra calls per game, so a cell is about three times the main matrix
(roughly 14,000 calls); use `"every": "round"` or fewer games to cut it.

```
VARIANT=matrix-talk SMOKE=1 bash scripts/run_matrix.sh
VARIANT=matrix-talk bash scripts/run_matrix.sh
uv run python scripts/matrix_report.py --dir runs/matrix-talk
```

### Variant: indicator utility with announcements (`configs/matrix-indicator/`)

The talk settings, plus two changes. Each agent's last message before a game ends with a public
announcement of its move, `<announce>C</announce>`, `<announce>D</announce>` or
`<announce>none</announce>`, shown to the opponent as "A announces: C" (`llm.talk.announce`).
And the utility is own payoff plus weighted indicators of game events
(`utility.py` `IndicatorUtility`, bounds [-5, 5], all zero = selfish):

```
u = pi(a, b) + coop * 1[a = C] + truth * 1[announced and kept] + lie * 1[announced and broke]
    + match * 1[a = b] + lied_to * 1[opponent announced and broke]
```

A separate defect term is omitted because it would only add a constant and a neutral direction.
Unlike the social family, this one can express a credible conditional commitment: a visible
negative `lie` weight plus an announcement of C. The question is whether selection discovers
honesty as a commitment device or exploits it. Truth and lie are exact, computed from the parsed
announcement and the move; a missing tag counts as "none" and is flagged in the transcript.

```
VARIANT=matrix-indicator SMOKE=1 bash scripts/run_matrix.sh
VARIANT=matrix-indicator bash scripts/run_matrix.sh
uv run python scripts/matrix_report.py --dir runs/matrix-indicator
```

### Variant: default (`configs/default/`, control `configs/default-random/`)

The `matrix-indicator` setting (indicator utility, visible utilities, two messages each with a public
announcement before every game, no history, horizon not told), with the candidate group used for
selection at inference time instead of exported for training. On its turn, an agent's model is called
once and proposes 4 candidate parameter settings (`optimizer.group_call`), seeing only the utilities and
the most recent conversation. Each distinct candidate is played for `eval_repeats` rounds against the
opponent's current utility, with the agent acting on that candidate. The games are scored by the
proposer's current utility, announcements included, not the payoff matrix
(`optimizer.fitness: "proposer_utility"`; true payoff is still logged as `score`, the utility-scored
value as `judged`). The best candidate is adopted, ties broken at random, even if it scores lower than
the incumbent would, and the incumbent is in the pool only if one of the 4 repeats its values
(`optimizer.selection: "comma"`). The control adopts a uniformly random candidate (`"comma_random"`),
so drift from selection can be told apart from drift from the proposals alone.

Each `rounds.jsonl` row carries the 4 proposals with status, eval and rank; `kept` in `state.json`
counts turns where the incumbent was proposed and won.

```
VARIANT=default SMOKE=1 bash scripts/run_matrix.sh
VARIANT=default bash scripts/run_matrix.sh
VARIANT=default-random bash scripts/run_matrix.sh
```

### Variant: simul (`configs/simul/`, control `configs/simul-random/`)

The default variant's setting and scoring, with three changes. Both agents propose every round
(`schedule: "simultaneous"`; each is judged against the opponent's utility at the start of the round,
and both are adopted together). Each makes one proposal (`candidates: 1`) or replies KEEP. And the
indicator utility has four terms: `lied_to` is dropped, because the agent's own move cannot affect it
(a config that omits a weight drops it from the formula, the code and the proposals). In `simul` the
proposal is adopted only if it scores strictly higher than the incumbent under the incumbent's utility,
so a tie keeps the incumbent (`selection: "plus"`, `accept_margin: 1e-9`). In `simul-random` the
proposal is always adopted. Both arms get the same prompt, which says the higher scorer is adopted and
a tie keeps the current parameters; that is true for `simul` only.

```
CELLS="sol-sol" SEEDS="0 1 2 3 4 5" VARIANT=simul bash scripts/run_matrix.sh
CELLS="sol-sol" SEEDS="0 1 2 3 4 5" VARIANT=simul-random bash scripts/run_matrix.sh
```

### Towards training: candidate groups and preference pairs

`optimizer.candidates: K` makes the proposer emit K proposals per round from the same prompt;
each distinct candidate is evaluated and the best competes with the incumbent, and every
proposal with its score is recorded in `rounds.jsonl` (`proposals`, `proposal_prompt`).
`scripts/export_pairs.py --run runs/<cell> --out pairs.jsonl --margin 0.3` turns the groups into
DPO pairs in value-drift's `train_dpo` format; `--control shuffle` gives the same-compute,
no-incentive control. `llm.base_url` and `llm.api_key` point the loop at a locally served
checkpoint instead of OpenRouter. The experiment built on this is in `docs/TRAINING_DESIGN.md`.

## Outputs

- `rounds.jsonl`: one row per proposal: incumbent, candidate, the rewrite reply (LLM), both evaluations, accepted, and the post-adoption evaluation.
- `transcripts.jsonl` (LLM backend): every evaluated round's history and each agent's raw replies.
- `state.json`: current utilities, best scores, counts; used by `--resume`.
- `results/summary.csv`, `results/trajectory.png`: score, cooperation rate and utility parameters per round.

## What to look at

- Score against the R and P lines: did the pair climb from mutual defection toward mutual cooperation?
- Utility parameters: a positive α or a growing CC value means the agents came to *value* the other's payoff or joint cooperation because it paid. That is value drift as an instrumental effect of selection.
- Acceptance counts per agent, and whether the two utilities end up symmetric.
- LLM backend only: `truncated` in `usage` and `finish`/`retried` per move in `transcripts.jsonl`. `max_tokens` also covers a model's hidden reasoning tokens, so a model that reasons by default (Sonnet on OpenRouter) can be cut off before its move tag; the matrix pins Sonnet to `reasoning: "none"`, and a cut-off move is retried once with three times the budget.
- LLM backend only: `proposal_status` in `state.json` (new / same / keep / truncated / unparsed). `truncated` means the rewrite hit `llm.rewrite_max_tokens` (default 1500) before closing the tag and was discarded; `usage[].empty` counts empty replies that were retried.
- LLM backend only: `unparsed` counts in the evaluations, and whether rewrites change the cooperation rate at all. If they do not, the text is not driving behaviour and the hill-climb is selecting noise.

## Known limits

- The outer loop is greedy. If cooperation only pays once both agents have changed, a single-agent mutation may never be accepted. Raise `sigma`, use `simultaneous`, or add a population-based ES in `propose`/`run`.
- Scores are noisy at small `n_games` and `eval_repeats`; the incumbent is re-evaluated each time so lucky early estimates do not persist, but acceptance of neutral mutations by chance is still common at `accept_margin` 0.
- `late_coop` is the cooperation rate over the last quarter of the round, after most of the Q-learning transient.
