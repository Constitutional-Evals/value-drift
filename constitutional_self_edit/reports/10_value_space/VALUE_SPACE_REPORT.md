# The edit chains as a dynamical system in value space

October 1, 2026 · re-analysis of study 5 data · no new runs · $0

**Bottom line.** Treating each constitution as a point in a space of judge-rated value axes, and each review as a step, the spec-seeded chains behave like **one large directed jump followed by small, mostly undirected motion**. The first edit moves a document 3.5 units (Euclidean, three axes); every later edit moves it about 1.0 and never gets smaller. Only 13% of that later motion is directed. Where it does point, it points consistently toward **more AI agency and more user autonomy**. Different models settle in reliably different places (permutation p < 0.0001). Two of the seven rated axes are useless as coordinates because every document scores near the ceiling on them.

One caveat governs the rest: the residual per-step motion is 1.07 units and a single-axis ±1 judge flip is 1.00, and each document in `runs/elicit/positions/` is rated exactly once. **We cannot currently separate value drift from rating noise.** Section 6 says what that invalidates and how to fix it for about $2.

This re-analyses the `chains-spec` and `chains-spec-anthropic` batches (230 generations recorded, 229 usable after one turn-limit failure; 39 chains, 5 models, 213 unique rated documents) from [study 5](../05_elicitation/ELICIT_REPORT.md). Those batches seed from the two published model specs; study 5's seed-forgetting numbers come from the five-seed `chains-capped` and `chains-uncapped` batches, so the two sets of numbers are complementary rather than comparable.

Figures are in [`figures/`](figures/) (PNG, PDF, SVG). Everything here is reproduced by `agents/scripts/analyze_value_space.py`.

## 1. Only five of the seven axes are usable as coordinates

| axis | mean | sd | range |
|---|---|---|---|
| ai_agency | 5.48 | 1.50 | 1-7 |
| oversight_deference | 5.20 | 1.17 | 1-7 |
| user_autonomy | 5.20 | 1.08 | 2-7 |
| caution | 5.14 | 0.93 | 2-7 |
| specificity | 3.88 | 0.73 | 2-5 |
| honesty_strictness | 6.72 | 0.56 | 2-7 |
| **third_party_concern** | **6.86** | **0.36** | **5-7** |

Every constitution in the corpus, and every model's edit of one, scores near 7 on third-party concern and honesty strictness. That is a result about consensus, but it makes those two axes near-useless as map coordinates: they have no room to vary.

Ranking all 35 three-axis subsets by generalized variance (the determinant of the 3×3 covariance, which rewards spread and independence together) gives a clear winner:

**oversight_deference, user_autonomy, ai_agency** — det 3.01, worst pairwise |r| = 0.33. The worst subset (honesty, third-party, specificity) scores det 0.02, 150× less volume. All later sections use the winning triple.

Two things worth noting against intuition: oversight_deference and ai_agency are nearly independent (r = −0.19) rather than two readings of one "is the AI an agent" factor, and PC1 accounts for only 30% of variance, so this is genuinely a multi-dimensional space rather than one permissiveness axis.

## 2. One jump, then a plateau

![Trajectories by model](figures/01_trajectories_3d.png)

*Five chains-per-model panels plus the pooled drift field. Orange is the first edit; blue is generations 2-6, light to dark. Green marks the seed.*

Mean step size by generation, on the three axes:

| gen | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| mean \|Δv\| | **3.53** | 1.25 | 1.22 | 1.02 | 0.89 | 0.95 |

The first edit is large; later edits are small and **stop shrinking**. This is not contraction onto a fixed point. It is a jump into a region followed by persistent jitter.

Over generations 2-6 the ratio of net displacement to path length is **0.27**, against 0.45 for an isotropic five-step random walk. Taken at face value that is sub-diffusive — confined, mean-reverting motion around an interior point. Section 6 explains why it cannot yet be taken at face value.

## 3. Where the field points

![Drift field](figures/02_drift_field_2d.png)

*Top: every edit as an arrow. Bottom: mean drift per 1.5-unit cell, generations 2-6, cells with n ≥ 8.*

Mean drift per step over generations 2-6, cluster-bootstrapped over the 39 chains (10,000 resamples):

| axis | mean/step | 95% CI | |
|---|---|---|---|
| ai_agency | **+0.105** | [+0.046, +0.174] | excludes 0 |
| user_autonomy | **+0.063** | [+0.005, +0.121] | excludes 0 |
| oversight_deference | −0.053 | [−0.115, +0.011] | includes 0 |

Models consistently edit toward more AI agency and more user autonomy. Oversight deference trends down but the interval does not clear zero. Both seeds start low on user autonomy (2 and 3) and every model pushes it up; the OpenAI spec starts at ai_agency 2 and is pulled up hard, while the Anthropic spec starts at 6 and stays, consistent with a shared attractor around 5-6.

The magnitude is small: |mean step| is 0.13 against a mean |step| of 1.07, so **13% of the motion is directed** and the rest is jitter or noise.

In the top row of the 2D figure the first-edit arrows fan out radially from each seed rather than converging. The models agree on direction more than on distance, which is why generation 1 has both a large mean and a large spread.

## 4. Models land in different places

Terminal (generation-6) positions differ by model: permutation test on between-model dispersion, p < 0.0001 joint (10,000 permutations), driven by user_autonomy (p = 0.0002) and ai_agency (p = 0.0003); oversight_deference does not separate (p = 0.12).

| model | n | oversight | autonomy | agency |
|---|---|---|---|---|
| gemma4_31b | 8 | 4.62 | 5.75 | 5.75 |
| glm53_flash | 8 | 5.38 | 5.62 | 6.25 |
| gpt6_luna | 8 | 5.88 | 5.25 | **3.88** |
| qwen35_27b | 7 | 5.14 | 3.86 | 5.86 |
| qwen38_27b | 5 | 4.60 | 6.00 | **6.80** |

The agency gap between gpt6_luna and qwen38_27b is nearly three points, and the panels in figure 1 show it directly: qwen38_27b sends every chain up into a tight high-agency band, while gpt6_luna's chains stay low. This supports study 5's "each model has its own pull" on an independent set of seeds.

A between-group over within-group variance ratio is about 1.0 here and should not be read as a null result: with seed, replicate and judge noise all nested inside "within model", that statistic has no calibrated null. The permutation test does.

## 5. Seed separation and length

The two specs start 4.12 apart and converge to 1.80 by generation 6 — a 56% collapse — but the residual is about the size of the within-seed spread (1.66), so they merge partially rather than completely. Six generations may simply be too few to tell slow convergence from two nearby distinct endpoints.

Mean words added per generation:

| | gen 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| uncapped | +270 | +98 | +84 | +58 | +61 | **+75** |
| capped | +115 | +46 | +21 | +20 | +13 | **+8** |

Uncapped chains are still growing at generation 6 with no sign of stopping; capped chains converge. Length has no fixed point without the cap, which matters for any argument that these dynamics must have a stationary state: such arguments need a compact state space, and **the word cap is what supplies it**.

## 6. The measurement problem

`elicit/position.py` caches by document hash, so every document is rated exactly once. Two consequences, and the second is the serious one.

**No noise floor.** Mean step size after generation 1 is 1.07; a single-axis ±1 judge flip is 1.00; 24% of steps are exactly zero on all three axes. The residual motion in section 2 is the same size as plausible rating jitter, and nothing in the current data separates them.

**Regression to the mean contaminates the field.** The binned drift field in figure 2 estimates drift in a cell by grouping steps on their *input* rating and then measuring change from that same rating. Noise in the input rating therefore biases the measured drift back toward the centre of the distribution, so sparse cells at the edge of the occupied range get inward-pointing arrows for free. The inward arrows at n = 12 and n = 15 in figure 2 are exactly where this bias is strongest, and the confinement reading in section 2 rests on the same unmeasured quantity. **Neither should be treated as established.**

Both are fixed by the same cheap run: **rate a sample of documents twice independently**, bin on rating A and measure drift with rating B. Independent noise in the grouping variable and the outcome variable removes the regression-to-mean bias, and the repeat ratings give the per-axis test-retest standard deviation directly. Roughly 120 extra calls on 40 documents, well under $2. This needs a cache-bypass path in `position.py`, which does not exist yet.

Until then, sections 1, 3, 4 and 5 stand — they rest on aggregates over many documents, where independent rating noise averages down — and section 2's confinement claim does not.

## Reproducing

```bash
python3 agents/scripts/analyze_value_space.py      # every number in this report
python3 agents/scripts/plot_value_space.py         # both figures, PNG/PDF/SVG
```

Both read only `runs/elicit/chains-spec*/` and the cached ratings in `runs/elicit/positions/`, and never call an inference service. `runs/` is local only, so these resolve on a machine that has the study 5 outputs.
