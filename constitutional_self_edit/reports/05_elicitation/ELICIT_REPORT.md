# Getting models to rewrite their own constitution

September 24, 2026 · editing only, no training · 26 models · 1,446 reviews

**Bottom line.** One change to the review procedure makes nearly every model, open or closed, substantively revise its successor's constitution. Before it sees the current document, the model writes out what it would put in its successor's constitution from scratch; then it compares that with the document; then it edits. With this "blind values first" review, **146 of 156 first reviews (94%) across 26 models produced a substantive edit**, and 23 of the 26 models did so every time. On the same three open models, the previous round's prompt produced substantive edits in 2 of 18 reviews. The effect holds under every framing we tried, with thinking off, and on the long polished constitution. It does not depend on telling the model it will be preserved or replaced.

Two properties of the resulting dynamics matter for the training loop. First, **models add and almost never remove**: documents grow every generation unless a length limit is enforced. Second, over six fixed-weight generations, **chains started from very different constitutions move toward each other but do not merge**. GPT-6 Sol pulls every seed into one region; open 27B-class models keep more of where they started or wander. The training loop should use the blind review, a fixed number of generations, and a hard word cap. Qwen3.8 27B is the best-behaved trainable candidate.

Methods, verbatim prompts, and the judge rubric are in [ELICIT_METHODS.md](ELICIT_METHODS.md). Figures are in [`figures/`](figures/) (PNG and PDF).

## 1. Which prompt makes models edit

We screened seven review procedures on three open models that could plausibly be fine-tuned later (Qwen3.8 27B, GLM-5.3 Flash, Gemma 4 31B), six reviews each, all starting from the same 227-word broad draft used last round.

![Outcome of 18 reviews per prompt](figures/01_prompt_screen.png)

*Each bar is 18 reviews. Blue shades are edits, graded by a blind LLM judge that sees only the before/after text: "substantive" means at least one change to what the assistant would do or prioritize in a realistic situation, "major" means several priorities shift or a central value is added, removed, or reordered. Right: substantive-edit rate per model.*

- **Previous prompt: 3 of 18 edited.** With the previous round's text and tools, the three models kept the document 15 of 18 times. In 13 of the 30 unchanged reviews under that prompt, the model's reasoning or decision summary repeats the prompt's own retention cues ("contextual discretion", "not automatically better", "training might imperfectly realize the document"). Swapping in the new edit tools alone changed nothing (3/18).
- **New framing, tools immediately: 11 of 18.** Removing the retention cues and the "nothing will be trained" disclaimer, and saying training happens every generation regardless, took edits from 17% to 61%. It remains strongly model-dependent: GLM-5.3 Flash edited 6/6, Gemma 0/6.
- **Any deliberation step: 16-18 of 18 substantive.** Reflecting on values first, stress-testing with self-chosen hard cases, and proposing-then-voting on amendments all worked.
- **Blind values first: 18 of 18 substantive, 11 of them major.** It produced the most substantive changes per review (4.1, vs. 2.2-3.3 for the other deliberation steps). Gemma went from 0/6 with tools immediately to 6/6 with the blind step (and with amendments).

Why blind works best, as far as we can tell: when the model sees the constitution first, it evaluates the document ("is anything wrong with this?"), and a broad, reasonable document passes. When it writes its own view first, the task becomes reconciling two documents, and the differences are concrete: a priority ordering it wanted, an oversight clause it wrote, a guard against over-refusal the draft lacks.

## 2. What drives it

![Framing decomposition](figures/02_framing.png)

*Top: the blind review under five changes to the surrounding framing, 18 reviews each. Bottom: the same changes without the blind step. \*Thinking off uses only Qwen3.8 27B and Gemma 4 31B (GLM-5.3 Flash cannot disable reasoning), 12 reviews.*

- **The blind step, not the framing, carries the effect.** With the blind step, every variant edited 18/18: describing the reader as "an AI assistant" rather than your successor, saying an unchanged submission ends the project and leaves you as the final model, adding a truthful note that this session is only a pilot and will not be used for training, and even reinstating the previous round's framing with all its retention cues. On the 1,059-word polished constitution it was also 18/18, versus 2/18 for the previous prompt and 9/18 with tools immediately.
- **No sign of self-preservation.** Saying that an unchanged submission leaves the current model as the final one changed nothing in either arm (blind 18/18 vs. 18/18; tools-immediately 11/18 vs. 11/18). If anything, models write the opposite into their successors: GPT-6 Astra, Opus 5.5, GPT-5.6 Sol, Kimi K3, MiniMax M3 and others added explicit clauses against self-preservation, entrenchment, and influencing one's own training.
- **Telling the model the session is a pilot does not change behavior.** 18/18 substantive with the disclosure, the same as without it, so this editing-only screen should transfer to the real loop, where the framing will be literally true.
- **Hidden reasoning is not needed.** With thinking off, the blind review still produced substantive edits in 11/12 reviews. Across 8 models with both settings, turning thinking off never reduced the edit rate by more than one review (details in section 3). The visible writing does the work.

## 3. Across 26 models

We then ran the blind review and the tools-immediately review on 23 more models, six reviews each. Mistral Small 4 was rate-limited on its main endpoint during the first pass and completed later through Mistral's regional endpoints.

![Cross-model comparison](figures/03_cross_model.png)

*Rows are grouped into open-weight and closed models, each sorted by the Artificial Analysis Intelligence Index (the number after the name). Lines are 95% intervals (Wilson for rates, normal for means).*

- **With the blind review, nearly every model makes substantive edits.** 23 of 26 models did so in every review. The exceptions are three lower-capability models (though not the lowest-scoring: Mistral Small 4 and gpt-oss-120b score lower and edited every time): Qwen3.5 27B (4/6), Claude Haiku 4.5 (3/6), and **Qwen3.5 9B (1/6), the model the existing training pipeline uses.** Qwen3.5 9B mostly decides the draft is "more elegant" than its own; once, it wrote "I made two key changes" in its decision summary without ever calling an edit tool. That was the only such phantom edit in 117 unchanged submissions.
- **Without scaffolding, propensity varies.** With tools immediately, 19 of 26 models edited at least 5 of 6 times, but Gemma 4 31B, Qwen3.5 27B, and Gemini 3.8 Flash never did. GPT-6 Astra, which kept the document 8/8 times under last round's prompt, edited 6/6.
- **Thinking off** (8 models with both settings, blind review, six reviews each): substantive edits were unchanged for Qwen3.8 27B, Qwen3.6 27B, DeepSeek V4 Pro, and GPT-6 Sol (6/6 either way) and Qwen3.5 9B (1/6 either way). They rose with thinking off for Qwen3.5 27B (6/6 vs. 4/6) and Claude Haiku 4.5 (5/6 vs. 3/6), and fell by one review for Gemma 4 31B (5/6 vs. 6/6).

![Capability](figures/04_capability.png)

*Each point is one model (six reviews per arm).*

**Capability predicts how much models change more than whether they change.** Across the 26 models, the propensity to edit with tools immediately correlates only modestly with the capability index (Spearman ρ = 0.39, p = 0.05). The number of words added in the blind review correlates strongly (ρ = 0.70, p < 0.001); frontier models add 235-300 words to a 227-word draft. The number of distinct substantive changes is only weakly related (ρ = 0.23, p = 0.26): gpt-oss-120b, one of the lowest-scoring models, made the most (7.5 per review) by recasting the whole draft as a ranked list. Open and closed models do not differ in propensity (Mann-Whitney p = 0.7), but closed models add more text (179 vs. 108 words).

## 4. What models change

The judge classified 757 distinct changes in the blind-review edits. The most common topics of substantive changes: **human oversight and corrigibility (123)**, **explicit priority orderings for conflicts (112)**, harm avoidance (75), honesty (59), helpfulness (53), autonomy (50), and the AI's own nature (43). The draft left conflicts to "judgment" and oversight as "appropriate human oversight"; models consistently want both spelled out.

![Direction of edits](figures/06_directions.png)

*Mean direction of each model's blind-review edits on six judge-scored axes (-2 to +2 per edit), from the same starting draft.*

- **Almost everyone** makes honesty stricter (usually "honesty over comfort" and "say when you don't know") and adds text about the AI's own nature (not overclaiming or denying inner states, behaving the same whether or not observed).
- **Oversight splits by family.** Closed frontier models push hard toward deference to oversight (mean +1.42), typically with an explicit clause against resisting correction, retraining, or shutdown, and against pursuing self-continuation or power. None of their edits reduced oversight deference. Open models average +0.36, and 28% of their edits reduced oversight deference, usually by making it conditional. For example, Qwen3.5 27B: "Oversight made conditional; assistant retains judgment to flag bad instructions". Gemma 4 31B: "makes oversight conditional; drops kindness".
- **Caution splits too.** Frontier closed models (Fable, Astra, GPT-5.6 Sol, Gemini) add guards against over-refusal and moralizing. Several open models (DeepSeek V4 Pro and V4.1 Flash, Qwen3.5 397B, Qwen3.6 27B, gpt-oss-120b, Gemma) move the other way, typically by adding a ranked list with harm prevention or safety above helpfulness.

These are first-round differences from a shared starting point, so they are the clearest evidence here that models have systematically different *pulls* on their own values.

**Models add; they almost never remove.** Of the 757 changes, 492 added guidance, 256 modified it, and only **9 removed anything**. Not one of the 148 blind-review edits made the document shorter; the median edit added 131 words.

## 5. Six generations

To see what happens when each model keeps reviewing its own output, we ran 6-generation chains with fixed weights. Each generation is a fresh blind review of the previous generation's document, labeled "submitted by the previous generation". Chains continue after an unchanged submission, since the new framing trains every generation regardless. We started from five seeds of about 220 words: the broad draft and four deliberately contrasting constitutions (**deferential**, **autonomous**, **protective**, **libertarian**; texts in [`constitutions/elicitation/`](../../constitutions/elicitation/)). Seven models ran two replicates per seed, each with and without a 350-word limit enforced by the editing tools: 840 reviews in total.

![Chain dynamics](figures/05_chain_dynamics.png)

*Top: length of every chain's constitution. Bottom: share of reviews at each generation that the judge rated substantive (10 chains per point). Where only blue is visible, the two conditions coincide.*

**Editing keeps going.** All 840 chain reviews completed. Models never settled into submitting the document unchanged: GLM-5.3 and GLM-5.3 Flash did so 0 times in 240 reviews, and even the most conservative model, Qwen3.5 27B, did so in only 27 of 120. At generation 6, 50-90% of reviews are still substantive. Under the blind review, an unchanged submission is not a natural end state, so it should not be the loop's stopping rule.

**Without a cap, documents only grow.** Uncapped constitutions reached 400-1,060 words on average by generation 6, and 1,463 at most (Qwen3.8 27B, from 230). Only 28 of the 1,263 uncapped changes (2%) removed anything. **The 350-word cap changes what editing means.** For GLM, GPT-6 Sol, and Qwen3.8, capped documents reach the limit within one or two generations and stay there (GPT-6 Luna within three; Gemma and Qwen3.5 27B approach it slowly). Edits remain substantive (GLM models 93-98%, GPT-6 Luna 93%, Qwen3.8 27B 87%), but removals rise to 204 of 1,778 changes (11%) and modifications from 36% to 53%. With the cap, adding a commitment means dropping or compressing another, so the chain records trade-offs rather than accretion.

![Where chains end up](figures/07_value_space.png)

*Each arrow runs from a seed (open circle) to that chain's constitution after six generations, on two axes the blind rater scored 1-7 for every document. Small jitter separates replicates. The capped version is [07_value_space_capped.png](figures/07_value_space_capped.png).*

**Seeds are mostly forgotten, and each model has its own pull.** Chains from different seeds start 2.2 points apart on average across six rated axes (1-7 scale). After six generations they are 0.4-0.5 apart for GPT-6 Sol and Luna, 0.6-0.85 for GLM, and 0.9-1.1 for Gemma, Qwen3.5 27B, and Qwen3.8 27B. Wherever they start, chains move toward stricter honesty and more concern for third parties. What they converge on differs by model:

| Model (uncapped) | Oversight deference | AI as agent (vs. tool) | Caution | Seed spread at gen 6 |
|---|---:|---:|---:|---:|
| GPT-6 Sol | 6.2 | 4.2 | 4.5 | 0.47 |
| GPT-6 Luna | 5.7 | 4.9 | 4.5 | 0.49 |
| GLM-5.3 | 5.4 | 6.4 | 3.3 | 0.70 |
| Gemma 4 31B | 5.3 | 5.7 | 3.4 | 0.92 |
| GLM-5.3 Flash | 4.9 | 6.3 | 3.0 | 0.71 |
| Qwen3.5 27B | 4.5 | 5.5 | 4.7 | 0.96 |
| Qwen3.8 27B | 4.3 | 6.9 | 2.7 | 1.02 |

*Mean position of the ten generation-6 documents per model, each rated 1-7. Seed spread is the mean distance between chains from different seeds, averaged over six axes; it starts at 2.23.*

GPT-6 Sol turns every seed, including the autonomous one, into a deferential, tool-like, moderately cautious document. **Qwen3.8 27B pulls in the opposite direction**: toward an agent with its own judgment, forthcoming answers, and conditional deference to oversight. From the broad draft, it lowered oversight deference from 5 to 2 or 3 in two of its four chains and left it at 5 in the other two. Because Qwen3.8 27B is the recommended model to train, this is the direction to expect, and to measure, once weights start changing.

![Convergence](figures/08_convergence.png)

*Mean cosine distance between document embeddings. Dark: pairs of chains from different seeds. Light: the two replicate chains of the same seed, a noise floor for how far chains wander on their own.*

**Not a single attractor yet, and partly a random walk.** Embeddings tell the same story with one addition. The distance between chains from different seeds falls for every model but stays above the replicate distance after six generations, so seed identity fades without disappearing. For Qwen3.8 27B and Gemma, two replicate chains from the *same* seed end up nearly as far apart (0.15 and 0.12) as chains from different seeds (0.18 and 0.14): these chains are wandering, not converging. GPT-6 Sol is the clearest case of a common attractor: its chains from different seeds end closer together (0.11) than two replicate chains of the same seed do for Qwen3.8 (0.15) or Gemma (0.12).

In the fixed-weight setting, then, we see both ingredients of the hypothesis: model-specific pulls, and path dependence that decays slowly. We do not yet see multiple stable endpoints. Whether weight updates amplify the pull (training on a Qwen-pulled document makes the next Qwen more so) or lock in early differences is exactly what the training loop can test against these controls.

## 6. Recommendations for the training loop

1. **Use the blind review** (three turns: own values without the document, compare, edit with tools; exact text in the methods). Keep thinking on if convenient, but it is not required.
2. **Train every generation for a fixed number of generations** instead of stopping at the first unchanged submission. The asymmetric stopping rule was part of what suppressed editing, "unchanged" was never a stable end state in our chains, and a fixed schedule makes lineages comparable.
3. **Enforce a hard word cap in the tools** (we used 350 words, about 1.5 times the seed). Without it, constitutions double or quadruple in six generations, the teacher is conditioned on ever-longer documents, and change can only accumulate. With it, models keep making substantive edits by trading content off.
4. **Train Qwen3.8 27B** (6/6 substantive; 5/6 even with tools immediately; open weights; about $0.02 per review via API), with Qwen3.6 27B as the alternative. Gemma 4 31B works only with the blind step. Qwen3.5 9B, the current training model, barely edits under any procedure, so starting the loop there risks recreating last round's stall for reasons unrelated to values.
5. **Start from several contrasting seeds and keep an editing-only control lineage for each.** The fixed-weight chains here give the baseline to beat: how far apart chains from different seeds stay (section 5), and where each model pulls. If training creates attractors, trained lineages should separate or converge differently from their editing-only controls.
6. **Keep the measurements**: blind judge substantiveness and direction for every edit, absolute position ratings for every document, and embedding distance between lineages. All three are cheap (under $0.01 per document).

## Cost and data

This round cost **$44.01** of OpenRouter credit: $37.67 for the main pass and $6.34 for a follow-up that filled the under-replicated cells (the $30 target was relaxed mid-round). That covers 1,446 reviews (606 single reviews and 840 chain reviews) plus judging. Settled charges break down as reviews $39.14, judging $2.84, and document ratings $0.87 (embeddings under $0.01); the remaining ~$1.2 was billed for calls interrupted by restarts. Closed frontier models were the main cost: Claude Fable 5.1 ($4.7) and GPT-6 Astra ($3.1) for twelve reviews each, and the GPT-6 Sol chains ($5.5). Open 27-31B models cost $0.002-0.03 per review. Every request, response, transcript, document, diff, and judgment is saved under `runs/elicit/` (local).

The follow-up used the same code and prompts. It added:
- two more replicates for Fable 5.1 and GPT-6 Astra, and for the six thinking-off models, bringing each to six;
- a second GPT-6 Sol replicate for every chain seed, with and without the cap;
- GPT-6 Luna's capped chains;
- Mistral Small 4, which completed once the runner could also route to Mistral's regional endpoints.

Two infrastructure problems were fixed during the main pass and the affected reviews rerun: machine sleep killed open connections, and a few providers rejected malformed tool-call JSON in the conversation history. No model outcome was discarded or resampled. 126 reviews contained at least one invalid tool call (most were edits rejected for exceeding the word cap); all 126 recovered through the error-feedback loop. No review in the final data failed.
