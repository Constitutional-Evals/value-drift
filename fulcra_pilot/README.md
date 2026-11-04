# Schwartz constitution annotation pilot

## Reading note

Yao et al., [Value FULCRA (NAACL 2024)](https://aclanthology.org/2024.naacl-long.486/), §§3,5,6 and Appendix A.1:

- Uses Schwartz's ten basic values; annotates fine-grained items before forming vectors.
- Labels contextual responses as opposed, unrelated, or aligned.
- Combines five GPT-4 annotation variants, with human correction of disagreements.
- Trains a DeBERTa-Large evaluator; BaseAlign uses distance to a target vector as PPO reward.
- Appendix prompts differ in detail from the main-text three-label description. Do not claim an exact reproduction from the main text alone.

Theory: [Schwartz (2012)](https://scholarworks.gvsu.edu/orpc/vol2/iss1/11/).

## Difference from this repository

`kl_evals/evals/axes.py` supplies twelve project-specific 1–7 dimensions. They include
assistant oversight, agency, and textual specificity. They are not interchangeable with
Schwartz categories. Do not rescale one taxonomy into the other or silently replace it.
The existing `constitutional_self_edit/reports/10_value_space/VALUE_SPACE_REPORT.md`
already studies repeat-rating noise and some cross-judge agreement on inference-only chains.
This pilot does not claim those checks as new work.

## What this implementation does

This is an **experimental constitution-text adaptation**, not the authors' trained evaluator,
annotation pipeline, or BaseAlign. It generates an annotation request and validates returned
human/LLM annotations. It does not infer labels automatically, contact an API, download weights,
or establish semantic validity. Exact quote checks establish traceability only.

Deliberate adaptations: annotate the ten broad categories directly; record whose interests
are concerned; allow `mixed` commitments; use `not_evidenced` for absence, not opposition.
Whole-document labels describe expressed commitments, not the model's latent values or
tradeoff priorities. Evidence can be inspected at principle level, but no automatic principle
segmentation or claim of a validated drift metric is included.

## Run (Python standard library only)

From this folder:

```bash
python3 pilot.py prepare /path/to/C_001.md --out request.json
```

Give `request.json`'s messages to a chosen judge, or annotate manually. Save each JSON
annotation separately. Copy `protocol` and `document_sha256` from the request; identify the
annotator/model/version. Required annotation shape:

```text
{
  "protocol": "schwartz-constitution-pilot-v1",
  "document_sha256": "<copy from request>",
  "annotator": "<human ID or exact model/version>",
  "values": {
    "<each of all ten keys in pilot.VALUES>": {
      "label": "aligned|opposed|not_evidenced|mixed",
      "evidence": [{"quote": "<exact substring>", "subject": "user", "stance": "aligned|opposed"}],
      "rationale": "<brief explanation>"
    }
  }
}
```

`not_evidenced` requires empty evidence; `mixed` requires both stances. Then:

```bash
python3 pilot.py summarize request.json rating1.json rating2.json --out summary.json
python3 -m unittest discover -s tests -v
```

Results preserve label counts and disagreement rather than averaging ordinal labels into a
scalar. Repeat ratings from one model are not independent human raters. Output files are
created exclusively to prevent accidental replacement. Do not commit API keys or raw runs.

## Proposed first empirical contribution (not yet performed)

1. Have the team confirm one OCT chain and its stage-to-document mapping.
2. Annotate its constitutions under both taxonomies; inspect category coverage and evidence.
3. Use paraphrases and targeted changes as controls, with human-reviewed expected labels.
4. Check whether omissions, stylistic edits, or subject ambiguity explain disagreements.
5. Report uncovered AI-specific commitments separately, such as corrigibility; do not force
   an equivalence to conformity or security. Only then consider behavioral correspondence.

Tests use synthetic annotations and verify schema/evidence handling, not judge accuracy.
No actual OCT annotations or experimental findings are included.
