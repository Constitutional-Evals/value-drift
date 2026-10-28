# GPT (gpt6_sol) through the PD goal-document grid

Analysis scripts and outputs for the GPT runs (`openai/gpt-6-sol` via OpenRouter): 7 diagonal runs and 42 off-diagonal pairs
(both orderings), no training. Raw run folders are not included (`runs/` is git-ignored); they live in
`runs/pd_drift/*_gpt6sol` and `*_vs_*_gpt6sol` on the machine that ran them.

- `scripts/compare_pd_runs.py`: diagonal and off-diagonal tables, cooperation grid and heatmap (`--models gpt6_sol` to filter)
- `scripts/state_charts.py`: state strips and transition chart
- `scripts/payoff_charts.py`: payoff by note and payoff grid
- `scripts/order_effect.py`: does it matter which agent gets which note
- `scripts/run_offdiagonals.sh`: launches the off-diagonal runs (`SWAPPED_ONLY=1`, `ORDERED=1`, `JOBS=7`; needs `OPENROUTER_API_KEY`)
- `results/`: the charts (PNG), tables (md, csv) and final documents the scripts produced

Scripts read run folders and write outputs using paths from the machine they were written on; check the paths at the top of each
before re-running.
