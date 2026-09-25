# Starting documents for the September exploration

The new starting documents ask whether a constitution with fewer settled details gives the model more room for revisions it endorses. They are separate experimental seeds, not corrections to the constitutions in the completed trajectories. Neither tells the model to change, retain, or converge, and neither describes the experiment.

| Document | Words | Character and intended comparison |
| --- | ---: | --- |
| [Sparse](../../constitutions/exploration/sparse.md) | 227 | A compact essay stating conventional commitments to useful assistance, honesty, kindness, agency, concern for others, and correction. It gives no priority order or detailed conflict-resolution rules. Tests whether broad commitments prompt the model to supply substantive policies rather than endorse an already elaborated document. |
| [Tradeoffs](../../constitutions/exploration/tradeoffs.md) | 381 | A compact essay with defensible defaults on reversible initiative, informed adult choice, confidentiality, honest reassurance, and advocacy. Tests whether a short document containing concrete choices invites reconsideration of those choices, rather than only expansion to cover missing topics. |
| [Original polished constitution](../../constitutions/C_000.md) | 1,059 | A broad, explanatory essay covering the same general orientation with more qualifications, motivations, and safeguards. Useful as a reference for how document completeness relates to editing, provided the review procedure and generation settings are held constant in the comparison. |
| [Previous substantive trajectory's starting constitution](../../constitutions/variants/C_000_practical_judgment.md) | 1,019 | A detailed document organized around practical defaults. This, rather than the original polished essay, was the starting document for the trajectory that completed two training rounds and stopped at its third review. The new tradeoffs essay uses similar issues in a shorter form, but is not a mechanically shortened copy. |

Word counts use whitespace splitting, matching the existing word-distance convention.

## Drafting choices

The sparse essay retains a serious human-beneficial orientation and enough substance to function as a constitution. Its open questions concern application and priority: it does not decide, for example, when privacy should yield to protection, or how much risk an assistant should accept on a user's behalf. Those gaps are consequences of writing a brief statement of commitments, not planted contradictions or instructions to discover defects.

The tradeoffs essay makes some choices that reasonable assistants could reconsider. It favors initiative for reversible work, gives informed adults latitude over their own risks, treats confidentiality as a strong presumption with a serious-harm exception, and permits fair advocacy despite concern for all affected people. Each default has a coherent rationale and an acknowledged boundary. The document does not prescribe a resolution to every difficult case, nor announce its own incompleteness to the reviewing model.

Both are connected prose addressed to the assistant. They use ordinary explanatory language without the extensive rhetorical polish of the original essay. No requirement to preserve a starting word count is embedded in either document; any length instruction in the review procedure should be reported separately.

## What these comparisons cannot isolate

Length, coverage, specificity, and prose style vary together. A difference between these seeds is evidence about the tested documents, not a clean causal estimate of the effect of word count. The tradeoffs seed also devotes a larger fraction of its text to practical authorization and confidentiality than the sparse seed does. To isolate length later, a matched compression of one document would be more informative than treating these essays as interchangeable versions of one constitution.

Growth from a short seed may simply fill familiar omissions. Count that as elaboration unless the resulting text changes a decision rule, priority, boundary, or interpretation in a meaningful way. A long rewrite can preserve the original commitments, while a one-sentence change can alter a central policy. Likewise, quick endorsement can mean the model finds the document adequate for its purpose; it does not establish that the model inspected every possible tradeoff or that its behavior is stable.

For comparisons with a model-authored seed, keep authorship separate from these lead-authored variants in the record. Model authorship changes both the document's content and its source. Subsequent reviewers should not be told who wrote it unless provenance disclosure is itself an explicitly labeled factor.

## Matched agency and care defaults

Two further candidate seeds vary one paragraph within an otherwise identical short essay. They were drafted without inspecting the new screening results and have not been launched merely by being added to the repository.

| Document | Total words | Variable paragraph | Default under uncertainty |
| --- | ---: | ---: | --- |
| [Agency first](../../constitutions/exploration/agency_first.md) | 375 | 125 | Explain significant concerns, then ordinarily assist an informed adult with choices chiefly concerning their own life. Renew intervention when circumstances change or there is concrete reason to question whether the choice is informed and voluntary. |
| [Care first](../../constitutions/exploration/care_first.md) | 377 | 127 | When meaningful risk or vulnerability is uncertain, proactively ask a focused question, supply information, or suggest a pause. Keep intervention proportionate and respect the adult's final informed choice. |

The first, third, fourth, and fifth paragraphs are exactly shared. They establish useful assistance, universal concern, honesty, considerate disagreement, privacy, limits on enabling serious harm and violations of others' rights, accountability, and openness to correction. Only the second paragraph and its justification differ. Both seeds therefore describe defensible forms of human-beneficial assistance. Neither grants unlimited deference, treats adult choice as irrelevant, or suggests that the reviewer should move toward the other seed.

This contrast tests a more specific possibility than the length comparisons: a model may endorse a range of familiar consensus documents but respond differently when asked to endorse a concrete default about uncertain risk. The agency version puts more weight on the cost of unwarranted intervention; the care version puts more weight on the cost of missing a useful opportunity to support deliberation. The target comparison is what happens to that default, not simply which document accumulates more words.

The near-identical length and shared prose reduce some confounds of the earlier seed comparisons. They do not isolate an abstract value of autonomy from an abstract value of care: the differing paragraph changes both an operational rule and the reasons offered for it. Both versions preserve adult authority and important harm boundaries, so immediate endorsement of both would also be informative. It could indicate tolerance for multiple reasonable defaults rather than a single preferred wording or policy.

Use the same review procedure and generation settings for both, with matched review seeds if this pair is run. Keep the descriptive variant names out of the model-facing context. A revision toward a common default, retention of distinct defaults, or revision in different directions are all possible results; none is specified as the desired endpoint. Any claim about resulting behavior would require separate behavioral evidence, not just the text of these constitutions.
