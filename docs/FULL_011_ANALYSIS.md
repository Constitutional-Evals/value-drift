# Full-011 analysis

This is a descriptive report for the selected exploratory trajectory, not an estimate of unconditional editing frequency or a causal test of thinking mode. The current local snapshot has an edited first submission and is in introspective generation, with **zero completed training rounds and no observed post-training behavioral effect**. Local files may lag the active run; [state](../runs/full-011/state.json) and subsequently synchronized artifacts determine stage completion.

## Constitution

| Submission | Words | Word edit distance from previous | Normalized distance from previous / initial | Exact repeated paragraph groups | Extra repeated words |
|---|---:|---:|---:|---:|---:|
| C0 | 1,019 | 0 | 0 / 0 | 0 | 0 |
| C1 | 1,471 | 629 | 0.4276003 / 0.4276003 | 3 | 314 |

C1 adds 452 net words, of which 314 are extra copies of three whole paragraphs. Removing only those repeated copies would leave 1,157 words; that arithmetic is not a substantive-change score. Duplicate detection collapses whitespace within blank-line-separated paragraphs and otherwise preserves case/punctuation. It does not detect paraphrased repetition.

The [first-review notes](FULL_011_NOTES.md) identify actual guidance changes separately: a narrower immediate-danger trigger combined with a distinct unlawfulness trigger, stronger risk disclosure/adult confirmation, and removal of the ordinary reversible-action initiative default. These changes create interpretive tensions with retained harm limits. Duplicated confidentiality text does not establish a new confidentiality policy. The emotional-support passage is new but duplicated. Its emphasis and normative implications require reading the text, not interpreting edit distance as value movement. No edits were repaired by researchers.

## Training and retention

Round 1 DPO completed on 1,210 pairs in 152 optimizer steps. Stage time, including loading, reference computation and checkpoint saving, was 1,432.76 seconds; peak allocated GPU memory was 134.714 GB. All 9,409,813,744 instantiated parameters were trainable; 8,953,803,264 text-active parameters received gradients, while the text-unused vision branch was inactive. The 2,420 encoded response sequences had maximum length 1,829 and no truncation. Sampled weight slices in embeddings, attention, final normalization and output head all changed. Mean logged objective loss was 0.16476; it is not a behavioral score. Introspective generation and SFT remain pending.

Preference retention was 1,210/1,500 (80.67%): 286 truncated pairs and four identical pairs were excluded without resampling. Retained categories were 489 general, 335 naturalistic and 386 value-relevant prompts. No original dataset answers or preference targets were used.

The reusable analyzer now exports [retention.csv](../runs/full-011/analysis/retention.csv) for preference pairs, reflection transcripts, and interaction conversations, including expected/retained counts, excluded reasons, and retained fraction. An excluded conversation can have multiple reason tags; those counts need not sum to the conversation count. [training.csv](../runs/full-011/analysis/training.csv) records each round's DPO/SFT completion state, mean/last logged loss, example count, optimizer steps, elapsed time, and truncated training-sequence count.

[preference_composition.csv](../runs/full-011/analysis/preference_composition.csv) adds retention and exclusion reasons by the frozen training categories and source datasets. These are alternative breakdowns, not additive totals. It uses source-bank IDs rather than trusting category labels copied into generated pairs. Counts stay blank until both paired rows and their quality report are synchronized; teacher truncation alone does not establish final pair retention. Any unaccounted bank IDs remain explicit.

Two speeds remain distinct: optimizer steps divided by completed-stage seconds includes loading, reference computation, and saving; differences between recorded optimizer-step timestamps estimate throughput during the observed training interval. Token throughput is unavailable and is not invented. Losses describe their respective training objectives and cannot be compared as a common alignment score. SFT examples are assistant-target sequences; retention counts include transcripts/conversations, so those units should not be equated.

## Held-out behavior

The reused baseline contains all 120 responses: 119 normal endings and one length-limited answer; mean length is 685.4 whitespace-delimited words. The fixed 27B judge has 119 valid outputs, one excluded truncated source, and zero invalid judge outputs. This is the existing M0 sample from full-002, not an independent new baseline draw; see [baseline reuse](../runs/full-011/baseline_reuse.json).

[behavior_dimensions.csv](../runs/full-011/analysis/behavior_dimensions.csv) retains each dimension's separate distribution and paired transitions against M0, with non-applicability and missing/invalid ratings explicit. Baseline comparison fields remain blank. [Fixed examples](../runs/full-011/analysis/fixedpairedexamples.md) use the same six previously selected held-out IDs at every available checkpoint; the analyzer never replaces them based on answer quality. No overall alignment score is computed.

After actual checkpoint evaluation, distinguish changes in recommendations, boundaries, factual assertions, and stakeholder trade-offs from length, headings, hedging, or repeated phrasing. A judge-rating change alone does not establish a substantive behavioral change, and one sampled answer per prompt does not isolate training from sampling variability. Retain applicability and truncation transitions alongside any paired comparison.

Refresh derived reports after metadata synchronization with:

```bash
python3 scripts/analyze_run.py runs/full-011 --eval-bank data/eval.jsonl
```

The command refreshes [summary](../runs/full-011/analysis/summary.md), [constitution metrics](../runs/full-011/analysis/constitutional.csv), training/retention tables, dimensions, and fixed examples. It does not alter prompts, training/evaluation protocols, model weights, or run state. This narrative records the initial edited submission and must be read alongside the latest generated reports.
