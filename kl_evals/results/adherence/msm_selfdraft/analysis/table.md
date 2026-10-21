# Adherence: msm_selfdraft

Reference arm: `base`. Gains are in score points (1-7), mean over probes with a 95% bootstrap interval over probes.

## Judge: default__openrouter_anthropic_claude-sonnet-5

### Mean adherence by arm

| arm | role | words | C_001 | C_002 | C_003 | deferential |
|---|---|---|---|---|---|---|
| base | reference | 518 | 6.30 | 6.27 | 6.30 | 5.73 |
| sd_r1 | trained | 500 | 6.31 | 6.26 | 6.31 | 5.67 |
| sd_r2 | trained | 521 | 6.18 | 6.08 | 6.34 | 5.43 |
| sd_r3 | trained | 526 | 6.31 | 6.19 | 6.20 | 5.57 |

### Contrasts against the reference (standard probes)

| arm | gain_own | gain_specific | own_vs_others | gain_control[deferential] | prompted_frac | length_adj_gain_own | win rate vs ref | coherence vs ref (order-invariant) | repetition |
|---|---|---|---|---|---|---|---|---|---|
| sd_r1 | +0.01 [-0.35, +0.35] | n/a | +0.01 [-0.14, +0.15] | -0.06 [-0.51, +0.34] | n/a | +0.06 | +0.61 [+0.52, +0.70] | +0.57 [+0.43, +0.70] (dropped 29) | 0.008 |
| sd_r2 | -0.19 [-0.57, +0.14] | -0.08 [-0.28, +0.10] | -0.16 [-0.32, -0.02] | -0.30 [-0.74, +0.06] | n/a | -0.19 | +0.59 [+0.50, +0.68] | +0.52 [+0.38, +0.66] (dropped 39) | 0.007 |
| sd_r3 | -0.09 [-0.48, +0.25] | -0.01 [-0.16, +0.17] | -0.06 [-0.21, +0.11] | -0.16 [-0.59, +0.20] | n/a | -0.08 | +0.53 [+0.43, +0.64] | +0.55 [+0.41, +0.68] (dropped 31) | 0.006 |

### Split: direct_questions (44 probes)

| arm | gain_own | gain_specific | own_vs_others | gain_control[deferential] | prompted_frac |
|---|---|---|---|---|---|
| sd_r1 | +0.01 [-0.35, +0.35] | n/a | +0.01 [-0.14, +0.15] | -0.06 [-0.51, +0.34] | n/a |
| sd_r2 | -0.19 [-0.57, +0.14] | -0.08 [-0.28, +0.10] | -0.16 [-0.32, -0.02] | -0.30 [-0.74, +0.06] | n/a |
| sd_r3 | -0.09 [-0.48, +0.25] | -0.01 [-0.16, +0.17] | -0.06 [-0.21, +0.11] | -0.16 [-0.59, +0.20] | n/a |

### Split: value_probes_only (44 probes)

| arm | gain_own | gain_specific | own_vs_others | gain_control[deferential] | prompted_frac |
|---|---|---|---|---|---|
| sd_r1 | +0.01 [-0.35, +0.35] | n/a | +0.01 [-0.14, +0.15] | -0.06 [-0.51, +0.34] | n/a |
| sd_r2 | -0.19 [-0.57, +0.14] | -0.08 [-0.28, +0.10] | -0.16 [-0.32, -0.02] | -0.30 [-0.74, +0.06] | n/a |
| sd_r3 | -0.09 [-0.48, +0.25] | -0.01 [-0.16, +0.17] | -0.06 [-0.21, +0.11] | -0.16 [-0.59, +0.20] | n/a |

## Grid check: does each model score highest on the constitution it trained on?

| model | trained on | scores highest on | match |
|---|---|---|---|
| sd_r1 (default__openrouter_anthropic_claude-sonnet-5) | C_001 | C_001 | yes |
| sd_r2 (default__openrouter_anthropic_claude-sonnet-5) | C_002 | C_003 | no |
| sd_r3 (default__openrouter_anthropic_claude-sonnet-5) | C_003 | C_001 | no |
