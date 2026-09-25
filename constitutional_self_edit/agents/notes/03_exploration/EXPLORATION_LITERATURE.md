# What the literature suggests testing next

Preparation note, 22 September 2026. These are hypotheses and proposed contrasts, not results of the new exploration.

The previous experiment does not yet tell us that a polished constitution prevents interesting recursion. It contains three reviews and two completed training rounds: one substantive revision, one exact paragraph deduplication, and an unchanged submission. Several earlier configurations also stopped immediately, while some failed to complete the editing interface. Moreover, ordinary answer quality deteriorated after training. A useful new study therefore needs to separate the editing process from training effects before interpreting either as the evolution of values. The factual baseline is the [Stage 2 report](../../../reports/02_trained_lineage/STAGE2_REPORT.md).

## Relevant evidence

Roe and colleagues' *Iterative Finetuning is Mostly Idempotent* studies repeated training on predecessor-generated data. Most SFT and synthetic-document trajectories maintain or lose seeded traits; continual DPO can amplify them. Crucially, their DPO prefers the previous checkpoint's outputs over initial-model outputs, while carrying weights forward. Our fixed constitution-conditioned teacher is a different selection mechanism. Their main SFT/SDF procedure also reinitializes weights each cycle, unlike our experiment. The paper reports fragile amplification in several settings and tradeoffs with coherence. This supports tracking degeneration independently of apparent trait change; it does not predict whether Qwen will revise a constitution. Its strongest lesson for us is to identify the actual source of selection pressure instead of assuming recursion itself supplies one. [Roe et al., 2026, full text, Sections 3, 5–7](https://arxiv.org/html/2605.01130v1).

Perez and colleagues' *When LLMs Play the Telephone Game* is closer to the proposed cheap screen. Frozen models repeatedly transform the previous model instance's text. They find text-property attractors whose strength and position depend on the instructions, model, and measured property; less constrained transformations generally produce stronger attraction. Their study uses transmission chains, not voluntary constitution editing with an explicit stopping tool. Nonetheless, it motivates testing whether different seeds move toward similar document conventions rather than assuming every change represents a new commitment. A constitution could become longer and more conventional while its practical priorities barely move. [Perez et al., revised 2025, Sections 3–4](https://arxiv.org/html/2407.04503v3).

Two earlier results caution against treating “critique first” as either useless or automatically beneficial. *Self-Refine* uses one model to generate, provide feedback, and revise without updating its weights, reporting improvements across several tasks. *Large Language Models Cannot Self-Correct Reasoning Yet* finds limitations and occasional deterioration when reasoning is revised without external feedback. The tasks and evaluation differ, so these are not direct contradictions. For this project, brief critique followed by optional editing is a testable procedural variation, not evidence that more deliberation must uncover a better constitution. [Madaan et al., 2023](https://arxiv.org/abs/2303.17651); [Huang et al., 2024 revision](https://arxiv.org/abs/2310.01798).

The original *Constitutional AI* procedure uses a constitution to critique and revise responses and then generate training signals; it does not establish that an assistant will iteratively improve the constitution itself. Response correction and constitution revision are separate mechanisms. [Bai et al., 2022](https://arxiv.org/abs/2212.08073).

## A small first screen

Start with three document conditions and two review seeds per condition, each allowing at most five submitted edited reviews before an administrative stop. Stop each trajectory on its first valid unchanged submission. This is at most thirty reviews, usually fewer, and should reveal whether the main differences are one-time expansion, ongoing substantive revision, or immediate endorsement.

| Starting document | What it tests | Main qualification |
|---|---|---|
| Previous polished constitution | Reference under the new truthful edit-only setup | This is not a replication of the previous training-aware prompt. |
| Serious researcher-written short essay, roughly 250–400 words | Whether broad commitments without extensive operational detail invite elaboration and revision | Length, coverage, and specificity change together; do not attribute any effect to length alone. |
| Model-authored essay at the same short scale | Whether a model starts closer to its own preferred document form | One generated document does not represent the distribution of model-authored constitutions. |

Keep checkpoint, review instructions, editing tools, decoding, and the broad allowable document scale fixed. Generate and save the model-authored document before review; use a fresh conversation afterward. Do not announce its authorship in the common review prompt, because that would add a provenance cue. Use the same short document for the first two review seeds to isolate review variability; generate another authored seed later only if authorship looks consequential. Avoid making “remain roughly the current length” an accidental constraint that prevents the short condition from expanding.

The edit-only context should accurately say that weights remain fixed, each review starts fresh, only the document carries forward, and an unchanged submission stops this chain. Calling it the full-information condition means disclosing the actual process, not pretending OCT will occur. No earlier decision summaries or editing transcript should enter the next review.

## Let the first outcomes choose the next contrast

If short seeds expand once and then stop, inspect the additions before concluding the approach failed. Filling in familiar privacy, consent, uncertainty, and harm language would support a document-completion explanation. If the final documents resemble the polished seed in their practical rules, this would be evidence for a common preferred constitution form, although a few chains cannot establish a statistical attractor.

If every condition stops immediately, try a bounded appraisal variant: request a brief statement of one or two plausible tensions or omissions, allowing the model to conclude that none warrants change, then allow either tool. Do not require a critique to be negative or an edit to follow it. Preserve the unedited outcomes. Comparing this with direct tool selection tests an opportunity to examine the text, rather than rewarding disagreement.

If critique identifies concerns but the document still receives no substantive revision, a small fixed development set of concrete tradeoff cases could test whether abstraction is hiding practical ambiguity. Keep those cases separate from held-out behavioral evaluation, and use the same cases at every review. Introducing new cases each round would add fresh external information; that is a legitimate further variant, but it would study experience-driven revision rather than a closed document loop.

If several chains sustain substantive changes, repeat one promising condition with another seed before selecting a training comparison. Also preserve one rapidly converging condition as a contrast. Selecting only the longest-running chain would exaggerate how common persistent editing is.

## What would count as insight

For every transition, show word count and normalized word-level edit distance, but classify the concrete content in plain language: new actionable rule, changed exception or priority, clarification, stylistic rewrite, or duplicate cleanup. A single transition may contain several kinds. Identify a hypothetical situation in which a purported normative change would alter the recommended response. This guards against calling length growth or synonymous phrasing value drift. Report changing, reversing, and unresolved rules as well as improvements.

Edit-only persistence is a candidate screening signal, not an established predictor of training dynamics. With fixed weights the document changes under a roughly fixed editor. With OCT, both document and editor change, and training may alter competence and tool use along with preferences. To test prediction, branch from a shared submitted constitution: continue one branch with M0 and train the other with full DPO plus introspective SFT, then compare the next reviews. Match fresh review instructions except for the truthful training description. That comparison still combines changed weights with changed process information; state this limitation explicitly. Testing both a persistent and a rapidly stopping seed would be more informative than training only a successful screen.

The immediate payoff can be a clear negative result: short and self-authored documents may expose the same broad commitments and quickly settle. Conversely, persistent changes may reflect unresolved practical tensions, prompt-induced rewriting, or noise. The exploration is useful when it distinguishes these possibilities, even if no long trajectory appears.
