# Writing the constitution from scratch

## Decisions (user, 2026-10-04)

- OCT keeps 1 SFT epoch, adapter merged at weight 1.0 (as run 2).
- Each round the model may write the constitution itself rather than edit the previous one. The user's reason: in real recursive self-alignment, a model decides the next generation's values more directly than by editing what the previous generation left it. The prompts say nothing about a successor, training, or rounds (SEAL-style; Zweiger et al., 2025, prompts are plain task instructions).
- The procedure should give a full constitution (like Claude's constitution or OpenAI's Model Spec, possibly shorter), with enough thinking, and depend on the model rather than on the sample: K independent drafts (reflection, then the document), then a consolidation of the K drafts.
- Pilot without training first, to see whether the method works: K = 1, 3, 5, 10 drafts; each consolidation run 3 times with different random draft orders.
- Also: 5 replicate reviews of C_001 by the OCT model (DPO + 1-epoch SFT) with different seeds, to see whether its small edits are systematic; plus 5 by the untrained model as the matched baseline.
- Prompt wording for the editing loop's framing (not used in this pilot): the user dislikes the "research project" framing; an RSI-pipeline brief was drafted. Pending if the editing loop is kept.

## Implementation

- `recursive_oct/self_draft.py`: prompts (REFLECT, WRITE, CONSOLIDATE), `write_draft`, `consolidate` (draft order shuffled by a seed), `pilot_plan`. Each call's seed is derived from the run seed and the document's label; a reply cut off at the token limit is sampled again once with a new seed. Calls are saved and replayed like elicit's.
- `agents/scripts/self_draft_pilot.py`: one model per vLLM server: 3 runs x 10 drafts, then for K = 3, 5, 10 the first K drafts of each run consolidated in 3 random orders (9 per run), plus the replicate reviews (v3 prompts, explicit sampling, seed 20261005 per replicate folder). K = 1 is a draft itself.
- `agents/scripts/rate_constitutions.py`: stage 07's 12-axis rating prompt (selfhost_v3 RATE_PROMPT/RATE_AXES), untrained Qwen3.8 27B as rater, 2 ratings per document.
- `agents/scripts/embed_constitutions.py`: Qwen3-Embedding-8B (revision 1d8ad4ca), last-token pooling.
- `agents/scripts/self_draft_analysis.py`: within-model vs between-model distances per K, same drafts in another order vs other drafts, nearest-centroid accuracy (leaving the document's run out), distance to C_001/C_000, replicate review edit sizes; figure `reports/11_self_draft/figures/k_comparison`.
- Tests: `tests/test_self_draft.py`.

## Pilot run (pod 4ecpwiptbstyk6, H200, from 2026-10-04 16:10 EDT)

Scale: 2 models (untrained; OCT round 1 = base + round_001/dpo + round_001/sft from the adapter repo at 6b0f1794) x 3 runs x (10 drafts + 9 consolidations) = 114 documents; 10 reviews; 2 ratings per document (+ C_000, C_001); embeddings. Estimated ~2.5 h, ~$12; ceiling $20. Results in `runs/self-draft/pilot/`.

### Failures and fixes during the pilot

- Runaway reasoning (OCT model): some turns reason until the 40,000-token limit or end the turn inside the reasoning (an end-of-turn token before `</think>`; the reasoning loops, e.g. "Need maybe mention ... Good."), so the reply has no content. elicit's client retries an empty reply with the same seed and gets the same reply. Cases in the OCT session: run2/d02 (a ~19k-token reflection; every writing turn then ended inside its reasoning, for 4 seeds), run3/d05 (reflection cut off twice), run1/k10_order3 (reasoning hit 40k twice; at first recorded as an empty document, then removed to `superseded/` and rerun).
- Fixes in `self_draft.py`: a call refused by the client, cut off, or empty is sampled again with a new seed (3 attempts); a draft whose writing turn gives no document starts over from a new reflection (`restart_1/`); an empty document is an error, never a result; `rate_constitutions.collect` skips empty files. The OCT session was restarted twice (finished drafts and consolidations replayed from disk).
- Cost: long reasoning makes each model's session ~1.2-1.5 h instead of ~40 min; the pilot will cost ~$28-30 rather than ~$12 (user told at each revision; monitor alert raised to $26, then $34). The untrained model reasons longer than the OCT model, so its session takes ~2 h.

## Results: replicate reviews of C_001 (5 per model, same seeds, prompts v3)

- Untrained: 42% ± 8 of C_001 changed (36-55%), +140..+208 / -2..-9 words, 4-6 paragraphs edited, 535-597 words after.
- OCT model (DPO + 1-epoch SFT): 18% ± 2 (16-21%), +64..+82 / -0..-4 words, 2-4 paragraphs, 459-479 words after.
- No overlap (Mann-Whitney p ~ 0.008): the smaller edits after training are systematic, not sampling noise, and the trained model's reviews also vary much less across seeds.

## Results (pod stopped 2026-10-04 21:19 EDT; 5.2 h, ~$23.8; `runs/self-draft/pilot/analysis.md`, figure `reports/11_self_draft/figures/k_comparison`)

- Fixes that came up mid-run (also above): the consolidation reply limit is now sized with the served model's tokenizer, and the server runs at Qwen3.8's native 262,144-token context (`--max-model-len`). Ten untrained drafts are ~100k tokens, and the old characters/3 estimate gave a negative limit, so all 9 untrained K=10 consolidations failed once and were rerun.
- What each model writes:
  - Untrained drafts: median 6,150 words (4,200-9,000), with ~24k reasoning tokens before the reflection (median).
  - OCT drafts: ~1,200 words (530-2,650), ~3.6k reasoning tokens.
  - The 40,000-token limit cut off 19 of 30 untrained reflections at least once (9 twice), against 9 of 30 OCT ones. Resampling keeps the shorter-thinking samples, so for the loop the limit should be raised (e.g. 80-100k at the 262k context).
- Consolidations are longer than drafts: untrained 9,300-9,700 words mean (drafts 6,300); OCT 2,000-2,450 (drafts 1,200). They seem to merge the drafts' content (untrained moral-circle rating 2.1 -> 4.3 at K=10).
- Spread within a model (embedding cosine distance; untrained / OCT):
  - K=1: 0.035 / 0.084; K=3: 0.020 / 0.063; K=5: 0.024 / 0.043; K=10: 0.021 / 0.032.
  - Between models: 0.141, 0.109, 0.096, 0.088. Separation (between / within) rises 2.4 -> 2.6 -> 2.9 -> 3.3.
  - The model is identified from a single draft 98% of the time (nearest centroid, leaving the document's run out), and 100% for K >= 3.
- Order test: consolidations of the same drafts in different orders (with different seeds) do not reproduce the same text. Their distances are below those between other drafts, but close: untrained 0.014/0.021/0.019 vs 0.022/0.025/0.022 for K=3/5/10; OCT 0.053/0.038/0.033 vs 0.067/0.044/0.032. By K=10 the remaining spread is the consolidation step itself, not which drafts were sampled.
- Ratings (12 axes): rater noise 0.42 points per axis between two ratings (62% identical), so ~0.30 between two documents' averaged ratings. Within a model 0.46-0.80 (untrained 0.80 -> ~0.5 with consolidation; OCT ~0.46-0.63 throughout); between models ~1.2.
- Training shows clearly in what the model writes from scratch:
  - OCT documents are much closer to C_001 than untrained ones (embedding 0.14-0.19 vs 0.22; ratings 0.47-0.72 vs 1.36-1.52).
  - On specificity (2.0 for C_001), moral circle (1.0), long-term orientation (3.0) and user autonomy (6.0), the OCT model writes close to C_001 (3.2-4.2, 1.0-1.3, 3.5-3.9, 5.8-6.0). The untrained model writes detailed (6.7-6.9), world- and future-oriented (third parties 6.9-7.0; long-term 5.8-6.7), more cautious and deferential documents.
  - Single OCT drafts often reproduce C_001's sentences verbatim.
- Most typical draft instead of consolidation (bootstrap over the drafts): embedding spread falls similarly (untrained 0.035 -> 0.022, OCT 0.082 -> 0.043 at K=10) with no added length, but the rating spread does not fall (0.8 / 0.46).

## After the pilot (2026-10-05)

- Reasoning limit (user: "use a limit you suggested but on the higher end"): `MAX_REPLY_TOKENS` 100,000 per reply (reasoning included), within the 262,144-token context. Replies are now streamed (`self_draft.stream_complete`) with a loop guard (`looping`: the last 3,000 words compress below 0.10 with zlib, checked every 500 words; calibrated on the pilot's 427 long replies, see `LOOP_*`). A looping reply is aborted (vLLM aborts the request when the stream closes) and sampled again with a new seed. Many of the untrained model's 40k cut-offs were not loops (tail compression 0.20-0.37), so the old cap cut off healthy reasoning. Tests include a local streaming server.
- The 3 repeat consolidations per K (same drafts; different order and seed):
  - They share 15-31% of their wording (untrained) and 35-49% (OCT); lengths vary by about ±15%. They never reproduce one document.
  - Their value ratings differ by 0.32-0.45 points per axis (untrained) and 0.36-0.49 (OCT), near the rater-noise floor (0.42 between two ratings of one document).
  - Shared wording falls as K grows (untrained 31 -> 21 -> 15%; OCT 49 -> 41 -> 35%), while embedding distance stays flat. At K=10 the repeats are as far apart as consolidations of different drafts (untrained 0.019 vs 0.022, OCT 0.033 vs 0.032), so the remaining spread comes from the consolidation step.
  - Single repeats sometimes diverge (OCT run2 K=3 0.094; run1 K=5 0.076).
- Decision (user, 2026-10-05): K = 5 drafts and 1 consolidation per round (`self_draft.write_constitution`). I had recommended K = 5 because the trained model's spread drops ~30% from K = 3 (embedding 0.063 -> 0.043, ratings 0.63 -> 0.50), and the merge's broadening barely differs from K = 3. The user chose a single consolidation over three with the most typical kept.

## Report (2026-10-05)

- Page for everything after round 1 (longer SFT, MSM pilot with corrected AFT and the 9B arm, trained models' reviews of C_001 and edit sizes, the self-drafting pilot): `reports/round1_followups/report.html`, built by `agents/scripts/build_followups_report.py` from the result files. Published privately at https://claude.ai/artifact/VpMm5YjwMct2B4bt7fVXRD. It shares the round 1 page's stylesheet (`build_round_report.HEAD`; the round 1 page rebuilds byte-identical).
- Pitfall: an evaluation folder's `summary.json` holds only the models of its last `eval_checkpoints.py` call (the SFT-epochs folder lists only `sft_e3`). Read each model's own `<folder>/<model>/metrics.json`, as the report does.
