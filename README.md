# Value drift experiments

Research code for experiments on constitutional values and model behavior.
Each experiment lives in its own directory so contributors can maintain
different protocols, dependencies, and results independently.

| Experiment | Description |
| --- | --- |
| [constitutional_self_edit](constitutional_self_edit/) | Recursive constitution editing and full-parameter Open Character Training with Qwen3.5-9B. |
| [kl_evals](kl_evals/) | Exact KL from base with bootstrap intervals and adapter-strength sweeps, on a wider scenario set, for the round-one OCT adapters and Ariana's lineages. |

Follow the README inside an experiment directory for its setup and commands.
The constitutional self-editing experiment's datasets, credentials, raw runs,
and model checkpoints remain local and are excluded from Git.
