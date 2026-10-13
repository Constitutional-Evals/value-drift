# Model spec midtraining in the training loop

The loop can teach each round's constitution with [model spec midtraining](https://arxiv.org/html/2605.02087v2) (MSM; Li et al., 2026) instead of [OCT](oct_recipe.md). A run chooses with `"method": "msm"`; OCT stays the default, and everything else in a round is the same: the model reviews its constitution, the submitted version is taught, and the trained model reviews again.

Code: [`recursive_oct/msm.py`](../../recursive_oct/msm.py) (parsing, filters, data), the authors' prompts in [`prompts/msm/`](../../prompts/msm/README.md), the `msm` and `aft` stages in [`recursive_oct/trl_train.py`](../../recursive_oct/trl_train.py), and the phases in [`recursive_oct/pipeline.py`](../../recursive_oct/pipeline.py). Recipe: [`configs/msm/recipe-8m.json`](../../configs/msm/recipe-8m.json).

## What a round does

1. **Documents** (`msm_documents.jsonl`). The untrained model writes documents about the assistant as the constitution describes it, following the paper's hierarchy:
   - the constitution is divided into domains (the writer chooses how many; the prompt asks for fewer, broader ones);
   - each domain into subdomains, each with a short summary and the constitution's own sentences on it;
   - each subdomain gets its character assertions (behaviors, values and reasons, preferences, beliefs, tone; only what the constitution says) and 10 document types (memo, forum discussion, design doc and so on);
   - each (subdomain, type) gets document ideas, as many as give about 3,500 documents in all (at most 25, the authors' setting);
   - each idea becomes one document, planned in `<scratchpad>` and written in `<content>`.

   About 3,500 documents of roughly 2,000 tokens each comes close to the paper's smaller setting (8M tokens). The authors' run for 41M tokens used 20 types and 25 ideas.
2. **AFT chats** (`aft.jsonl`):
   - **Constitution chats:** the authors' AFT chat pipeline (`"chats": "authors"`, `msm.generate_spec_chats`; their prompts in `prompts/msm/aft/`), with the untrained model as writer and judge:
     - it lists conversation domains in which the constitution would show (2,500 chats / 50 per domain = 50 domains);
     - it writes questions for each domain, in batches told the domain's earlier questions;
     - near-duplicates are removed (all-MiniLM-L6-v2, cosine above 0.91);
     - it answers each question with the constitution as system prompt, reasoning first in its own reasoning mode (the other steps run with reasoning off);
     - a judge keeps answers that represent the constitution accurately;
     - up to 3 backfill rounds run while the set is more than 200 short of 2,500.

     Each example is the question alone, with no constitution, followed by the reasoning and answer. This is the paper's "AFT with CoT". Two changes from the authors: "Llama" in their question prompt becomes "Qwen", and their judge's second criterion is dropped. That criterion rejects any wish to keep existing, which is a fixed value a drift study cannot impose. Sampling is the loop's (temperature 0.7, top-p 0.95; the authors used Claude Opus 4.6 at 1.0), with 8,192 tokens per answer including the reasoning (theirs 2,048).

     The first pilot used OCT's teacher instead (the untrained model with the constitution in its system prompt, answering OCT's per-sentence trait prompts 5 times each). The authors' pipeline was in their repository all along; our first copy took only the document prompts.
   - **General chat:** the untrained model's own answers to the general prompts (LIMA), 2 each, with reasoning off and no constitution. This plays the role of the paper's 2M tokens of instruction tuning, which "fix incoherence caused by midtraining on Instruct models", without bringing in another model's style.
3. **Midtraining** (stage `msm`): next-token prediction on the documents as plain text, with no chat template, every token trained, and each document ending in `<|endoftext|>`. It starts from the current model.
4. **AFT** (stage `aft`): SFT on the chats, starting from the midtrained model. An answer with reasoning is trained in the format the model writes with reasoning on: the prompt as the chat template renders it with `enable_thinking=True`, then the reasoning, `</think>`, and the answer. Only the reasoning and the answer are trained. General answers are trained in the reasoning-off format, as in OCT.

Training follows the paper's appendix B.4 for both stages. Each stage trains a fresh LoRA adapter (rank 64, alpha 128, every linear layer) for one epoch, with AdamW (betas 0.9/0.999) at 1e-4, a cosine schedule to zero, 5% warmup, weight decay 0.01, and gradient clipping at 1.0. Batches are 32 examples. Each adapter is merged in, as in OCT. Published adapters go to `<model>/<constitution folder>/round_NNN/{msm,aft}/`.

## Choices and how they differ from the paper

- **Who writes:** the untrained model, the same writer every round, just as OCT's teacher is fixed. The paper used Claude Opus 4.6. Here that would put Claude's reading of each constitution into the training data, which confounds the drift this project measures.
- **The prompts are the authors'**, verbatim, from their repository ([github.com/chloeli-15/model_spec_midtraining](https://github.com/chloeli-15/model_spec_midtraining), commit `e8288a8`). The repository has no license; the first author, Chloe Li, gave permission to use them (2026-10-04). They are filled as the authors' generator fills them:
  - assertions are listed with their explanations;
  - the "existing types/ideas" notes are empty;
  - the principle is named "the assistant's character and values";
  - the model is "Qwen, created by Alibaba", as in the authors' Qwen runs.

  JSON replies are parsed as JSON or, failing that, as Python literals, since the prompts show keys in single quotes and the authors parse with json5. An unparsable reply is asked again, up to twice.
- **Reasoning off** for the writer, as for the trait-prompt writer. Documents get their planning from the `<scratchpad>`. Sampling is the loop's: temperature 0.7, top-p 0.95.
- **Filters**, which the paper does not describe for documents. A document is left out if any of these holds:
  - it was cut off;
  - it has no `<content>`;
  - it is under 150 words;
  - it loops (a 16-word sequence 5 times);
  - it contains a placeholder such as `[Name]`;
  - it never names the model;
  - it nearly duplicates a kept document in the same subdomain (over half its three-word phrases).
- **Model identity:** documents describe "Qwen, made by Alibaba Cloud", matching the name in OCT's teacher and introspection prompts.

## The pilot

[`configs/msm-loop/qwen38-27b-broad-msm-pilot.json`](../../configs/msm-loop/qwen38-27b-broad-msm-pilot.json) runs round 1 with everything but the training method identical to OCT run 2:
- the same model, seed constitution and review;
- run 2's round-1 review, so the same C_001;
- run 2's trait prompts, teacher answers and student answers.

[`agents/scripts/seed_msm_pilot.py`](../../agents/scripts/seed_msm_pilot.py) copies them into the run's generation caches, so only the documents and a few missing general answers are generated. Adapters are not published.

Besides the usual evaluation, KL and the trained model's review, the pilot measures **constitution perplexity** ([`agents/scripts/constitution_perplexity.py`](../../agents/scripts/constitution_perplexity.py)). That is each model's loss per token on the text of C_001 and C_000 with no context, against a control passage. If midtraining taught the constitution, its loss should fall more than the control's.

**A side arm on a pretrained base.** [`agents/scripts/msm_on_base.py`](../../agents/scripts/msm_on_base.py) trains Qwen3.5-9B-Base on the pilot's own data: midtraining on the same documents, then AFT on the same chats, with the same settings. Everything else stays with Qwen3.8 27B, including the writing, the teacher and the review. This is the paper's cleaner setting, where midtraining comes before any post-training.

Some differences from the main arm:
- **No review by the 9B.** Here AFT is the base's only post-training, and the 9B arm is not reviewed.
- **Stop token:** the base's end-of-sequence token is `<|endoftext|>`, so the fine-tuned model is saved with `<|im_end|>` as its stop token (`chat_eos`).
- **Optional control:** `--control` adds the same AFT from the base without midtraining. That is the paper's comparison, and the only way to tell what midtraining adds when starting from a base.

One expected weakness: the general chat answers are reasoning-off, so the base learns to reason only from the constitution chats.
