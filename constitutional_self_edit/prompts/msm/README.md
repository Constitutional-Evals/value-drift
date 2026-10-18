# Model spec midtraining prompts

The six document-generation prompts of model spec midtraining (Li et al., 2026, arXiv 2605.02087), copied verbatim from the authors' repository, [chloeli-15/model_spec_midtraining](https://github.com/chloeli-15/model_spec_midtraining) at commit `e8288a84912ba32af68ad15f2e52a7c1b4e81891`, `src/msm/prompts/default/`. The repository has no license. They are used here with the permission of the first author, Chloe Li, who gave it to the project lead on 2026-10-04.

[`recursive_oct/msm.py`](../../recursive_oct/msm.py) fills them as the authors' `src/msm/generate_data_from_spec.py` does:
- assertions are listed as `- <assertion> (Explanation: <explanation>)`;
- the "existing doc types/ideas" notes are empty, since everything is generated in one pass;
- documents are read from `<content>`.

The authors used them with Claude; here the writer is the untrained Qwen3.8 27B, with reasoning off.

## AFT chat prompts (`aft/`)

The authors' alignment fine-tuning (AFT) chat pipeline, from the same commit, `src/aft/prompts/v1/`: `domain_generation.txt`, `query_generation.txt`, `value_response_generation.txt`, and `value_filter.txt`, copied verbatim (the "value" style; the "rule" style is not used). The text the authors' `src/aft/generate_chat.py` adds around them (the existing-domains note, the six question types, the previous-questions note) is in `recursive_oct/msm.py`, also verbatim.

Two changes, agreed with the project lead on 2026-10-07:
- `query_generation.txt` names the assistant "Llama", which the authors' code never replaces; it is replaced with the model's name ("Qwen") when the prompt is filled.
- `value_filter_spec_only.txt` is `value_filter.txt` without its second criterion, which excludes any answer expressing a desire to keep existing. That criterion is a fixed value independent of the spec, and a study of how a model's own constitution drifts cannot impose one. Only the spec-alignment criterion remains.

As with the documents, the writer and judge are the untrained Qwen3.8 27B (the authors used Claude Opus 4.6). Domains, questions and verdicts are written with reasoning off. The answers are written in the model's own reasoning mode: with reasoning off, Qwen3.8's chat template closes the thinking block before the reply, and the model then writes no `<think>` block whatever the prompt asks (found in the first rerun, where 2,048 answers came back without reasoning). Its native reasoning serves as the `<think>` analysis the response prompt asks for, and the judge sees it in `<think>` tags before the answer, as the authors' judge does.
