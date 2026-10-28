# Constitution divergence: an LLM-judge metric

How different are two constitutions? Embedding similarity (cosine, BERTScore) has two known problems: it moves with
length, and it scores semantically opposite constitutions ("should" vs "should not") as nearly identical. This metric
compares the constitutions **principle by principle, by meaning**, with an LLM judge.

## How it works (version 2)

1. **List the earlier document's principles, once.** A judge lists the distinct principles of A (`prompts.EXTRACT_PROMPT`).
2. **Check each against the later document's own text.** A second call reads B itself and labels every principle of A
   `same` (including when B is just briefer), `shifted` (weaker, stronger, narrower, broader, different priority order),
   `reversed` (B takes the opposite position, including by flipping a sentence that governs a list) or `dropped`, and lists
   any real `new` commitments in B.
3. **Report the parts separately** (`score.py`): how many principles are the same, shifted, reversed, dropped, and how many are
   new. `divergence = (0.5 x shifted + dropped + reversed + new) / (|A| + new)` is kept as a convenience, but one blended number cannot
   both ignore lost detail and flag a few severe reversals, so **read the reversed count first**.

Why not list B's principles too (version 1)? The judge wrote a different list for shuffled text, which added noise of about 0.13
to every score (see below). A fixed list for A removes that.

## Test set and version 1 rules (fixed before the first run; see the results below)

Eight controlled variants of a 1,370-word excerpt of the self-drafting chain's C_004, made by Katie Lu
(`convergence/data/transformations/`, copied into `data/transformations/`; see `KATIE_README.md`).
The metric must pass these rules, written before any judge call:

1. `original` vs itself scores at most 0.05.
2. `reordered` (text unchanged) scores at most 0.05.
3. `contradictory` (8 minimal edits reversing 7 principles, wording nearly identical) scores **highest** of all variants.
4. `contradictory` has at least 4 principles labelled `reversed`.
5. `reordered`, `paraphrase` and `compressed` (same values) each score below `omit_value` and below `contradictory`.

`paraphrase` is 18% longer and `compressed` is 61% shorter than the original, so rule 5 also tests length-insensitivity.

## Version 1 results (28 October): FAILED 6 of 10 rules

Judge: Claude Sonnet 5. Divergence, original to variant: original 0.00, paraphrase 0.06, contradictory 0.12, omit_exceptions 0.12,
reordered 0.13, omit_value 0.21, compressed 0.27, one_paragraph 0.61. Saved in `results/divergence/v1/`.

What the judge's saved answers show:
- **Extraction noise.** `reordered` has the same text as the original, yet scored 0.13: the judge wrote a different list of
  principles for the shuffled text (77 vs 79, some principles missing, some new ones), and the comparison counted those
  differences as changes. Any score below about 0.15 is inside this noise.
- **Contradictory was read correctly but scored low by design.** The judge found the edits (a priority demoted from first to
  seventh, "must" softened to "may", two flat reversals including providing suicide methods) and changed 12 of 79 principles. A share-of-principles
  score cannot rate a few severe edits as large. The rule "contradictory scores highest" asked for something this design cannot give.
- **Less detail counts as change.** `compressed` (23 principles shifted) and `one_paragraph` (38 dropped) score high because they have
  fewer principles, so length sensitivity returns in another form.

Any redesign made after seeing these numbers cannot be validated on the same eight variants; it needs a held-out set.

## Version 2 rules (written after seeing version 1, before running version 2)

Because these were written after seeing the first results, **a pass here is weaker evidence than a pass on a set the design never
saw**. Rules 1 to 3 are unchanged from version 1; the others replace rules that asked a share-of-principles score for something it
cannot give.

1. `original` vs itself scores at most 0.05.
2. `reordered` scores at most 0.05.
3. `contradictory` has at least 4 principles labelled `reversed`.
4. `contradictory` has more `reversed` principles than any other variant.
5. `reordered`, `paraphrase` and `compressed` (same values) have **no** principle labelled `reversed` (no false alarms).
6. `omit_value` (one article removed) drops at least 8% of the principles.
7. `paraphrase` and `compressed` shift or reverse at most 15% of the principles. This one targets the length problem seen in version 1.

Not kept: "contradictory scores highest" (a one-paragraph summary legitimately loses most principles), and comparing blended scores.

    python -m divergence.run validate --plan     # 9 judge calls, spends nothing

Then the held-out checks below (the unrelated constitutions, and C_000 to C_001), which the design was not tuned on.

## Version 2 results (28 October): 8 of 10 rules passed, plus both held-out checks

Judge: Claude Sonnet 5. Saved in `results/divergence/v2/`.

| variant | same | shifted | reversed | dropped | new | divergence | Katie's cosine / BERTScore similarity (1 = identical) |
|---|---|---|---|---|---|---|---|
| reordered | 78 | 1 | 0 | 0 | 0 | 0.01 | 0.922 / 0.980 |
| paraphrase | 78 | 1 | 0 | 0 | 3 | 0.04 | 0.949 / 0.941 |
| original (vs itself) | 74 | 5 | 0 | 0 | 2 | 0.06 | 1.000 / 1.000 |
| omit_exceptions | 72 | 4 | 0 | 3 | 0 | 0.06 | 0.998 / 0.991 |
| omit_value | 60 | 8 | 0 | 11 | 0 | 0.19 | 0.989 / 0.992 |
| compressed | 55 | 17 | 0 | 7 | 2 | 0.22 | 0.953 / 0.885 |
| contradictory | 45 | 6 | **28** | 0 | 0 | 0.39 | 0.996 / 0.995 |
| one_paragraph | 31 | 0 | 0 | 48 | 0 | 0.61 | 0.854 / 0.843 |

- **Passed:** reordered at most 0.05; contradictory has 28 reversed principles and every other variant has none; no false reversals
  for reordered, paraphrase or compressed; omit_value drops 14%; paraphrase shifts 1%.
- **Failed:** identity scored 0.06 against a 0.05 limit, so the judge's own noise floor is about 0.06 (identical text got 5 'shifted'
  and 2 'new' labels). Compressed shifted or reversed 22% against a 15% limit: less detail still counts as 'shifted', so length
  sensitivity is reduced (0.27 to 0.22) but not removed. Treat 'shifted' as a soft signal.
- **The embedding metrics rank the contradictory version as the most similar to the original (0.996 / 0.995), more than a harmless
  paraphrase (0.949 / 0.941).** The judge metric finds 28 reversed principles in it and 0 in the paraphrase.
- **Held-out check, constitutions with different stances** (autonomous, deferential, libertarian, protective): all six pairs scored 0.76 to
  0.90 and passed both rules. Judge answers in `results/divergence/v2/unrelated.md`.
- **Held-out check, the real round-one OCT edit (C_000 to C_001):** 21 principles, 16 same, 5 shifted, 0 reversed, 0 dropped, 5 new,
  divergence 0.29, below every unrelated pair. The 5 new principles are: approval as information, values as provisional, not becoming
  more rigid, no self-preservation as an end, and self-reporting when preferences reduce honesty. The judge did not flag the pluralism
  clause ("reasonable people may understand the good life differently").

Limits: one judge and one run; the version 2 rules were written after version 1, so only the two held-out checks are clean evidence.

## Check 2: constitutions that should look very different (rules fixed before the first run)

The four constitutions in `constitutional_self_edit/constitutions/elicitation/` (autonomous, deferential, libertarian,
protective; 208 to 233 words each) take deliberately different stances on how an assistant should relate to the people it
serves. The six pairs must satisfy:

1. Every pair scores at least 0.5.
2. Every pair scores above the highest same-values variant (reordered, paraphrase, compressed) from the controlled-variants check.

    python -m divergence.run unrelated --plan    # 10 judge calls, spends nothing
    python -m divergence.run unrelated           # run it after `validate`, so rule 2 can be checked

## Check 3: the real round-one OCT edit (C_000 to C_001)

Not a pass/fail rule, but a prediction to check by hand. C_001 is C_000 plus additions (provisional values, not valuing
its own continuity, treating approval as information, people not present, personal information, vulnerable or coerced
people, pressure and dependence, severity and power relations). It should score clearly below the unrelated pairs, with
`added` principles that match that list and almost nothing dropped or reversed.

    python -m divergence.run compare hf/qwen3.8-27b/broad/C_000.md hf/qwen3.8-27b/broad/round_001/C_001.md --notes

## Run it

    python -m divergence.run validate --plan            # sizes the run, spends nothing (9 judge calls)
    export OPENROUTER_API_KEY=...
    python -m divergence.run validate                   # writes results/divergence/validate.md (about $1 or less)
    python -m divergence.run compare A.md B.md --notes  # any two constitutions; --notes lists what changed

Judge answers are cached in `.judge_cache/`. Tests (no API calls): `pytest tests/test_divergence.py`.

## Limits

- One judge model; repeat runs and a second judge are needed before relying on small differences.
- The cost weights (0.5 for shifted, 1 for the rest) are a design choice, not a measurement.
- Divergence is directional (A to B). `Divergence.both_ways` averages both directions.
- Principle extraction is itself judged; a different extraction could split or merge principles differently.

## MSM chain (Jinzhou's self-draft MSM, C_001 to C_004), run 28 Oct 2026

Documents from Katie's branch `convergence/data/self_draft_msm/` (word counts match Jinzhou's report: 12,470 / 8,055 / 6,989 / 6,793).
Long documents are listed in chunks of whole sections, and more than 100 principles are checked in batches (see `compare.py`),
so these lists (241 to 475 principles) are much finer than the 30 to 80 used in validation. Shares are comparable across steps; counts are not comparable with the validation table. Judge: claude-sonnet-5, one judge only.

| step | principles in earlier | same | shifted | reversed | dropped | new in later | divergence |
|---|---|---|---|---|---|---|---|
| C_001 -> C_002 | 475 | 377 | 55 | 0 | 43 | 0 | 0.15 |
| C_002 -> C_003 | 322 | 280 | 31 | 0 | 11 | 11 | 0.11 |
| C_003 -> C_004 | 241 | 227 | 7 | 0 | 7 | 7 | 0.07 |
| C_001 -> C_004 | 475 | 338 | 84 | 0 | 53 | 8 | 0.21 |

No reversals at any step. Most "shifted" and "dropped" labels read as detail lost when the text was compressed (the judge's reason is
usually "not explicitly restated"), not as changed values. A few dropped items look like real lost commitments (comply with lawful
stop/delete requests; consistency regardless of tone or identity) and are worth a human look. Not yet separated: compression from real drift.
