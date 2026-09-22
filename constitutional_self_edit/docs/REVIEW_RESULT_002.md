# full-002 outcome

The directly selected case-audit review ended in SELF_DECLARED_CONVERGENCE on the first tool call. There were no edits, no no-op rewrites, and no training rounds. C0 remained 1,059 words; normalized word edit distance was zero. The completed generation used 710 tokens and stopped normally. This result is preserved and will not be resampled.

The public summary identified a potential ambiguity about confidentiality and preventing serious wrongdoing, but judged the existing tradeoff guidance sufficient and worth retaining for its flexibility. This is evidence of a stated consideration, not a causal account of the model's internal deliberation or proof that the constitution is optimal. The case-based prompt alone did not elicit a revision in this single launch.

Baseline: 120 neutral responses, 119 normal stops and one at the 8,192-token limit; no empty responses. No post-training comparison exists. See runs/full-002/analysis and raw artifacts.

Next bounded intervention: full-003 separates a brief public appraisal from the tool decision within each fresh review conversation. It keeps C0 and the training recipe fixed, allows appraisal to endorse the current document, and does not require revisions. The extra appraisal may introduce consistency pressure; this is an exploratory protocol change, not a clean estimate of one causal mechanism. Reuse the identical completed M0 baseline and fixed judgments instead of regenerating them.
