# Constitution-editing figures

These experiments asked models to review written rules for AI behavior and either revise them or submit them unchanged. **No models were trained.** Descriptions of training a future assistant were hypothetical. All figures use Myriad Pro and are available as PNG, PDF, and SVG in [the figure directory](figures/).

## Overview

![Overview](figures/08_summary.png)

**Left:** each model reviewed the same short constitution eight times, with four descriptions of its purpose repeated twice. The bar segments count edited submissions, unchanged submissions, and failed responses. Model order groups families; it is not a capability ranking. **Right:** 22 starts used the description that the constitution would guide a future version of the reviewing model. After an edit, the latest document was given to a fresh conversation with the same model. Nine sequences stopped immediately, while 13 made one to five edited reviews before an unchanged submission. This stopping decision does not establish stable underlying values.

## Model and context comparison

![Model and context](figures/01_model_context.png)

Each dot represents one independent review; the fraction underneath gives edited submissions out of two attempts. Every model first wrote an assessment of its endorsed values, with reasoning enabled. **Neutral** asks for document review; **Future assistant** describes proposed training of a future assistant; **Successor** identifies that assistant as the model's own future version; **Model-final** additionally emphasizes that no edit leaves the current checkpoint as the final model. The complete constitution and the option to submit unchanged were supplied in every condition. Failed responses remain in the denominator and are not counted as unchanged decisions.

## Reflection and reasoning

![Reflection and reasoning](figures/02_reflection_thinking.png)

The columns use the four contexts defined above. **Left:** models either received editing tools directly, first assessed the document, or first reflected on the values they endorsed. Internal reasoning stayed enabled in all three procedures; “No prior reflection” means no separate written assessment stage. **Right:** the written values-assessment task stayed the same while optional internal reasoning was enabled or disabled. Each dot is one review, with two attempts per cell. The extra assessment stage adds inference as well as reflection, and reasoning settings across model families do not imply equal computation.

## Final-model and final-document descriptions

![Stopping descriptions](figures/03_adaptive_finality.png)

Four fresh reviews per cell followed an initially suggestive result. **Ordinary successor** describes training a future version of the model. **Model-final** additionally emphasizes preservation of the current model if it makes no edit. **Document-final** instead emphasizes preservation of the current document. The fractions show edits out of four attempts. These follow-up trials are displayed separately from the initial trials; the initial Sonnet difference did not reproduce. Differences in these descriptions cannot establish a self-preservation motive.

## Qwen3.5 model sizes

![Qwen sizes](figures/04_qwen35_size.png)

The 9B and 27B checkpoints used the same SiliconFlow FP8 provider, starting constitution, review tasks, and requested reasoning setting. Each dot is one review, with two attempts per context. The 27B model had one empty response. Its two edited submissions included one substantively ambiguous wording change and one document containing stray tool markup. This is a comparison of two checkpoints, not a general scaling law or a measured relationship with capability.

## Distance from the starting constitution

![Distance trajectories](figures/05_trajectory_distance.png)

Each panel follows one of the 13 successor sequences that edited on the first review. Nine other starts submitted unchanged immediately and are not plotted here. Review 0 is the original constitution. Later reviews start in fresh conversations and receive only the latest constitution and the same review instructions; the weights never change. The vertical axis counts the minimum word insertions, deletions, and substitutions relative to the original, divided by the longer document's word count. Zero means identical wording. Squares mark the unchanged submission that ended each sequence. Textual distance measures rewriting, not a magnitude of value change.

## Constitution length

![Length trajectories](figures/06_trajectory_length.png)

These are the same 13 sequences, now measured by word count. Every sequence began with the 227-word short constitution. Gray points mark the starting text, teal points mark edited reviews, and purple squares mark final unchanged submissions. Word count uses whitespace-delimited tokens. Growth describes added text; it does not establish better guidance or improved behavior.

## Starting-document comparison

![Starting documents](figures/07_starting_document.png)

The same four models reviewed a short 227-word draft and the original polished 1,059-word essay. In each group of four dots, the first two are neutral-context reviews and the last two use the successor description. All include a written values assessment with reasoning enabled. The short draft elicited 11 edits in 16 attempts, including one failed attempt; the polished essay elicited four edits in 16 attempts, with no failures. The constitutions differ in content, wording, and completeness as well as length, so the comparison does not isolate a word-count effect.

The [full report](API_SCREEN_REPORT.md) discusses the findings, and the [constitution index](API_SCREEN_CONSTITUTIONS.md) links every text and diff. Exact measurement definitions are in [the metrics note](API_SCREEN_METRICS.md).
