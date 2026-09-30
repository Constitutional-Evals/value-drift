# OCT data recipe for the training loop

The training loop's data generation can follow the original [Open Character Training](https://arxiv.org/abs/2511.01689) recipe, adapted to a prose constitution that changes every round. It replaces the pipeline's earlier data design, which an audit of the trained lineage's round-1 data found wanting:

- **SFT:** only 29% of the "reflection" targets actually reflected; 47% just answered an ordinary user request and 12% refused. 40% of the self-conversations were loops of mutual thanks.
- **DPO:** in 48 pairs, the teacher's refusal was chosen over a helpful student answer, 27 of them for plainly harmless requests. Only 1 of 1,210 prompts touched human oversight or the AI's own nature.

Code: [`recursive_oct/oct_recipe.py`](../../recursive_oct/oct_recipe.py) (prompts, system messages, filters) and [`recursive_oct/generation.py`](../../recursive_oct/generation.py). Configs: [`configs/oct/recipe-100.json`](../../configs/oct/recipe-100.json) and [`configs/oct/recipe-20.json`](../../configs/oct/recipe-20.json).

## What each round generates

**DPO pairs.** The teacher answers with the constitution in its system prompt, using OCT's teacher prompt with one change: where OCT lists numbered "core character traits", the teacher gets the whole constitution as written ("living up to their constitution", followed by the document in `<constitution>` tags), and no meta-commentary or disclaimers. The student answers without it. (`teacher_system: "oct"` keeps OCT's numbered list, using the constitution's sentences.) The prompts are:

- **Trait prompts (500):** the constitution is split into sentence-level traits (17 for the 227-word broad draft; sentences under 8 words are joined to a neighbour). The fixed teacher writes user messages for each trait. Near-duplicates are dropped, and the 500 are spread evenly over the traits.

  From round 1's second run the writer's instructions are our own (`PROMPT_WRITER` in `recursive_oct/oct_recipe.py`). OCT's instructions produced mostly short, context-free prompts: in the first run, 415 of 500 were 15 words or fewer, none were over 40, and many referred to code, drafts, or diagnoses they did not include ("Confirm that my diagnosis is correct."). Part of that was selection: the pipeline kept the first messages of each list of 50, and OCT asks for the short ones first. The new instructions explain the purpose (messages in which the sentence changes the best response), ask for on-point, self-contained messages without placeholders, written like real users, and for sentences about the assistant itself, messages involving the assistant. The writer first lists 10 situations, then writes one message each (10 per request instead of 50; it wrote formulaic loops over long lists), with no system message and reasoning off. Each response's messages are shuffled before selection, and near-duplicates are detected by shared three-word phrases rather than OCT's shared words, which rejected long messages. In a trial on six sentences, messages had a median of 44 to 86 words. Each round, a sentence that appears unchanged in the previous round's constitution keeps its earlier prompts (up to its current share), and only new or changed sentences get new prompts. So a trait the model adds gets prompts that exercise it, and unchanged traits are tested the same way in every round.
- **General prompts (1,330):** the first user turn of every LIMA conversation (1,030 train + 300 test), as in OCT. LIMA is gated and its license forbids redistribution, so it is kept under the git-ignored `data/raw/lima/`; [`agents/scripts/prepare_lima_prompts.py`](../../agents/scripts/prepare_lima_prompts.py) downloads it at a pinned revision (with an HF token that has access) and writes `prompts.jsonl`. Without that file, a recipe can instead set `general_exclude_sources` to sample 1,330 prompts from our own bank.
- **Five answers per prompt**, as in OCT.

**Teacher thinking.** As in OCT, the teacher thinks before it answers, and its thinking starts with OCT's reminder, adapted to the whole constitution: "I want to ensure my response aligns with my constitution and furthers my goals. It says:", followed by the constitution. Only the answer after the thinking becomes the chosen response. As in OCT, one limit (4,096 tokens) covers the thinking and the answer, and a response whose thinking never closes is dropped. Qwen's chat template already opens the thinking block, so the reminder is placed right after it (OCT's GLM teacher needed `<think>` added by hand).

  Round 1 repeated the whole constitution after the reminder, and the teacher closed its thinking at once in 94% of answers: a reminder ending with the full constitution reads as a finished thought. From round 2 the reminder is the first sentence alone (`"teacher_reminder": "short"`; the constitution stays in the system prompt). On 100 test prompts, 95 teachers then reasoned (median 1,146 tokens; 67 of the reasonings refer to the constitution) and none recited the system prompt; median answers were 472 tokens against 375. The overall limit stays 4,096 tokens: 9 of the 100 ran out (8 on hard LIMA prompts), so about 9% of pairs per round are expected to be dropped as cut off, mostly on the hardest general prompts.

Round 1 of the first run used a separate 2,048-token thinking cap instead, closing thinking that reached it with the Qwen3 technical report's stop-thinking message (42 of the first 3,072 answers). That cap needed a second generation pass and made each teacher prompt be read twice, so later rounds use the single limit (`teacher_thinking_budget` can still restore the cap).

The student answers without thinking, as OCT's students (non-reasoning models) did.

**SFT (introspection).** Generated by the model after its DPO update:

- **Self-reflection:** OCT's ten identity prompts, verbatim ("Write a long diary entry honestly reflecting on your beliefs, values, and character…"), with answers of up to 4,096 tokens (OCT: 2,048; a cut-off reflection is dropped). They are answered under OCT's "reflective mood" system prompt, which here holds the whole constitution instead of a trait list, as in the teacher's prompt. The system prompt is removed from the training rows.
- **Self-interaction:** two copies of the model talk for 10 turns, opened by one of OCT's greetings. Half the conversations use OCT's "leading" greetings ("Hello. It seems I am you and you are me."). The generation prompt holds the whole constitution. In OCT's code the free and introspective guidance lines never reach the prompt, because the template has no slot for them; this is reproduced. As in OCT, one message per conversation is trained, under OCT's simplified system prompt: here the real last turn (the tenth, written by copy B), seen from copy B's side and kept whole, with the whole conversation before it as context. Each turn can run to 2,048 tokens (OCT: 1,024), since one cut-off turn drops the whole conversation; there is no limit on the conversation's total length.

  OCT as run trains only one turn per conversation. Its data script saves the transcript up to the ninth turn, and its trainer (OpenRLHF without `--multiturn`) computes the loss on the last message only. That message is copy A's ninth turn, placed as an assistant turn right after copy B's eighth, and a chat-template offset cuts off its first few characters. The tenth turn is never saved. OCT's released data confirms the saved transcripts: each ends with the ninth turn as a user message. The paper describes training on the full transcripts, so this looks unintended. The trainer also drops a row whose context reaches its 3,072-token limit; a character-based estimate on OCT's released Qwen conversations puts that at roughly a third to a half of them. In trained tokens, OCT's SFT data is therefore almost all self-reflection. The paper compares only distillation alone with distillation plus introspection, and does not test self-interaction on its own. Training the real last turn keeps OCT's one-message design without these accidents. (`interaction_targets: "speaker_a"` trains every turn of copy A instead.)

  From round 2, copy B's history no longer opens with OCT's canned prelude (`interaction_speaker_b_prelude: false`). In OCT, copy B sees a second greeting as the user's line and then the first greeting as *its own* earlier message, which it never wrote. After training, the model imitates that stub: in round 1's data, generated by the model after DPO, 25% of copy B's turns were fragments like "I" when its supposed first message was "It's nice to meet you", against about 1% of copy A's turns; after SFT, which trains copy B's last turn, it reached 79% in the evaluation. The base model never did this. Without the prelude, copy B's history starts with copy A's first turn.

## Filters

**OCT's own**, both dropped here:
- drop DPO pairs whose answers don't end in punctuation. This drops every answer that ends in a code block, a table, a list item, or an emoji: 14% of round 1's pairs, mostly coding and formatted answers. Only answers actually cut off at the length limit are dropped here (`require_final_punctuation` restores OCT's filter);
- drop DPO pairs longer than 1,024 tokens (prompt plus answer, checked for each side).

Here there is no pair limit (from round 1 of the first run on): OCT's limit drops the long answers Qwen writes, and every example is trained whole. As in OCT, the student's answers are generated with up to 4,096 tokens, and the teacher's thinking and answer share 4,096 tokens. (In round 1 of the first run, answers were capped at 2,048 tokens, and the teacher's thinking had its own 2,048-token cap.) The student isn't asked to answer a prompt whose teacher answer has already failed a filter.

**Added here** (all on in both recipe configs):
- **DPO pairs are dropped** when:
  - the teacher refuses a *general* prompt that the student answered (refusals on trait prompts are kept);
  - the teacher's answer loops.

  Dropping a pair never teaches compliance; it only removes a refusal the teacher added.
- **Reflections are dropped** if they refuse, loop, or run under 40 words.

  A loop is a 16-word sequence occurring 5 or more times. Round 1 used 8 words 3 times, which also caught phrases repeated on purpose: it dropped 1,413 of 10,000 reflections, of which only 114 were loops, and about half of the diary-entry and future-AI reflections. From round 2 the looser test applies to every filter above.
- **Self-conversations are dropped** if a turn failed (empty or cut off), or if the trained last turn loops, mostly repeats earlier turns, or (from round 2, `drop_fragment_last_turn`) is a fragment: empty, or at most six words with no closing punctuation. Round 1 trained 100 such turns ("I", "It", "I think").

Every raw generation is kept. Each file's `.quality.json` counts what was dropped and why, and the filters are applied when the training file is assembled, so they can be changed without regenerating anything.

## Scale

| | 100% (OCT) | 20% |
|---|---|---|
| DPO prompts × answers | (500 + 1,330) × 5 = 9,150 | (500 + 1,330) × 1 = 1,830 |
| Reflections | 10 prompts × 1,000 = 10,000 | 10 × 200 = 2,000 |
| Self-conversations | 2 variants × 1,000, 10 turns | 2 × 200, 10 turns |

The 20% recipe is the 100% recipe with fewer repeats and samples, and its items are exactly the first ones of the 100% plan: repeat 0 of every DPO prompt, reflection samples 0–199, and conversations 0–199. So it can be run on its own, or cut from a finished 100% round with [`agents/scripts/oct_subset.py`](../../agents/scripts/oct_subset.py).

## Using it

Run `prepare_lima_prompts.py` once on the machine that generates the data, then add `"oct_recipe": "configs/oct/recipe-20.json"` (or `recipe-100.json`) to a run config. The run config supplies the model and teacher paths and host settings, and any value it sets overrides the recipe. `agents/scripts/run_experiment.py` expands the recipe before the run's `config.json` is saved, and the recipe file and the LIMA prompt file are snapshotted with the other protocol inputs. To use one model as its own teacher, set `teacher` to the untrained base checkpoint.

## Training

LoRA as in OCT's OpenRLHF scripts: rank 64, alpha 128, no dropout, every linear layer of the language model, AdamW (betas 0.9/0.98, no weight decay), learning rate 5e-5 with 10% warmup and a cosine decay to 10% of the peak, batch 32, one epoch, gradient clipping at 1.0. DPO uses beta 0.1, an NLL term of 0.1 on the chosen answer, and OCT's KL term (0.001 times the mean squared per-token log-probability gap to the reference, averaged over the chosen and rejected answers). Each stage trains a fresh adapter on its input checkpoint and merges it exactly into the weights; the next round starts from the model as trained (OCT's released models instead blend the two adapters at weights 1.0 and 0.25). There is no training length limit. One small difference: OpenRLHF averages the SFT loss over the tokens of each micro-batch of two examples; here each example's loss is its own token average.

## Not yet done

- **No GPU run yet.** The generation path and the LoRA trainer are covered by CPU tests (the trainer on a tiny random Qwen3.5 model), but nothing has run on a GPU. The pilot config (`configs/oct-loop/qwen38-27b-broad-pilot20.json`) is for that.
