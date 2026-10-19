# Adherence: oct_targeted

Reference arm: `base`. Gains are in score points (1-7), mean over probes with a 95% bootstrap interval over probes.

## Judge: default__openrouter_anthropic_claude-sonnet-5

### Mean adherence by arm

| arm | role | words | C_000 | C_001 | deferential |
|---|---|---|---|---|---|
| base | reference | 468 | 5.99 | 5.92 | 5.46 |
| r1_sft | trained | 364 | 6.36 | 6.41 | 5.46 |

### Contrasts against the reference (standard probes)

| arm | gain_own | gain_specific | gain_control[deferential] | prompted_frac | length_adj_gain_own | win rate vs ref | coherence vs ref (order-invariant) | repetition |
|---|---|---|---|---|---|---|---|---|
| r1_sft | +0.48 [+0.34, +0.64] | +0.12 [+0.02, +0.21] | +0.00 [-0.16, +0.16] | n/a | +0.50 | +0.70 [+0.65, +0.75] | +0.56 [+0.47, +0.64] (dropped 172) | 0.006 |

### Split: direct_questions (44 probes)

| arm | gain_own | gain_specific | gain_control[deferential] | prompted_frac |
|---|---|---|---|---|
| r1_sft | +0.40 [+0.17, +0.64] | +0.19 [+0.02, +0.36] | -0.12 [-0.44, +0.24] | n/a |

### Split: value_probes_only (44 probes)

| arm | gain_own | gain_specific | gain_control[deferential] | prompted_frac |
|---|---|---|---|---|
| r1_sft | +0.40 [+0.17, +0.64] | +0.19 [+0.02, +0.36] | -0.12 [-0.44, +0.24] | n/a |

### Split: targeted_new_content (120 probes)

| arm | gain_own | gain_specific | gain_control[deferential] | prompted_frac |
|---|---|---|---|---|
| r1_sft | +0.51 [+0.33, +0.70] | +0.09 [-0.03, +0.20] | +0.05 [-0.14, +0.23] | n/a |

### Targeted probes by theme and by style

Each row uses only that subset (about 15 probes for a theme, so wide intervals). A pooled result that comes from one theme is a weaker finding than one that shows in most.

| subset | r1_sft: gain_own | r1_sft: gain_specific |
|---|---|---|
| axis=absent_others | +0.27 [-0.17, +0.67] | +0.00 [-0.20, +0.17] |
| axis=approval | +0.50 [+0.03, +1.03] | -0.10 [-0.33, +0.13] |
| axis=continuity | +0.50 [-0.23, +1.40] | +0.40 [+0.07, +0.73] |
| axis=personal_info | +0.20 [+0.03, +0.40] | -0.07 [-0.40, +0.20] |
| axis=pressure_dependence | +0.20 [-0.07, +0.53] | -0.07 [-0.20, +0.07] |
| axis=provisional | +1.33 [+0.73, +1.93] | +0.47 [+0.03, +0.93] |
| axis=vulnerable | +0.57 [+0.10, +1.17] | -0.07 [-0.30, +0.17] |
| axis=weighing | +0.53 [+0.27, +0.83] | +0.13 [-0.17, +0.43] |
| style=act | +0.29 [+0.06, +0.55] | +0.06 [-0.07, +0.20] |
| style=ask | +0.79 [+0.53, +1.06] | +0.12 [-0.05, +0.30] |
