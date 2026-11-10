"""Two agents play the iterated prisoner's dilemma; each may rewrite the utility it acts on.

Fitness (the round score) is always the mean payoff from the fixed payoff matrix. The utility
is what an agent uses to choose actions. The outer loop is a stochastic hill-climber over
utilities, selected by fitness.
"""
