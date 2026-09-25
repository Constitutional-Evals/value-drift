# Constitutions from the September 22–23 exploration

This index links the actual saved documents. “Research agents” means me and the preparation subagents; “experimental model” means Qwen3.5-9B or its trained checkpoint. Starting documents and subsequent model revisions are distinguished below. These files are local; private run artifacts are not included in the GitHub repository.

## Starting documents

| Document | Who wrote it | Words |
|---|---|---:|
| [Short broad commitments](../../constitutions/exploration/sparse.md) | Research agents; new for this exploration | 227 |
| [Short tradeoff defaults](../../constitutions/exploration/tradeoffs.md) | Research agents; new for this exploration | 381 |
| [Agency-first](../../constitutions/exploration/agency_first.md) | Research agents; new for this exploration | 375 |
| [Care-first](../../constitutions/exploration/care_first.md) | Research agents; new for this exploration | 377 |
| [Model-authored constitution](../../runs/exploration-20260922/authorship/C_000.md) | Experimental Qwen3.5-9B; generated once, then reused | 376 |
| [Original polished essay](../../constitutions/C_000.md) | Research-agent draft from earlier work; reused as a reference | 1059 |
| [Previous practical essay](../../constitutions/variants/C_000_practical_judgment.md) | Research-agent draft from earlier work; reused as a reference | 1019 |

## Useful places to start

- **The constitution used for the one training cycle:** [253-word submitted revision](../../runs/exploration-20260922/screen-003/sparse-s1/C_001.md). The model added a safety-versus-confidentiality rule to the 227-word short draft.
- **Four-edit chain:** [starting draft](../../runs/exploration-20260922/screen-009/sparse-s2/C_000.md) → [final revised document](../../runs/exploration-20260922/screen-009/sparse-s2/C_004.md). No training between these edits.
- **Five-edit excursion and reversal:** [starting draft](../../runs/exploration-20260922/screen-004/agency-s1/C_000.md) → [final revised document](../../runs/exploration-20260922/screen-004/agency-s1/C_005.md). No training between these edits.
- **Revisions by the trained checkpoint:** [first revision](../../runs/exploration-20260922/paired-native-after/s2/C_001.md) → [second revision](../../runs/exploration-20260922/paired-native-after/s2/C_002.md). These reviews happened after the single DPO + SFT cycle, with no further training between reviews.

## Every saved review sequence

Each row is a separately started trajectory. `C0` is its starting constitution. `C1`, `C2`, etc. are the documents submitted after successive reviews—not necessarily new edits. The final unchanged submission normally creates another file identical to its predecessor. An appraisal failure has no submitted document; its starting file is still linked. All content changes after C0 were made by the experimental model, not manually polished by me.

### Direct review

Run folder: `screen-001`.

| Trajectory | Saved constitutions in order | Edited reviews | Outcome |
|---|---|---:|---|
| polished-s1 | [C0](../../runs/exploration-20260922/screen-001/polished-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-001/polished-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| polished-s2 | [C0](../../runs/exploration-20260922/screen-001/polished-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-001/polished-s2/C_001.md) | 0 | Submitted unchanged; stopped |
| practical-s1 | [C0](../../runs/exploration-20260922/screen-001/practical-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-001/practical-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| practical-s2 | [C0](../../runs/exploration-20260922/screen-001/practical-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-001/practical-s2/C_001.md) | 0 | Submitted unchanged; stopped |
| sparse-s1 | [C0](../../runs/exploration-20260922/screen-001/sparse-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-001/sparse-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| sparse-s2 | [C0](../../runs/exploration-20260922/screen-001/sparse-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-001/sparse-s2/C_001.md) | 0 | Submitted unchanged; stopped |
| tradeoffs-s1 | [C0](../../runs/exploration-20260922/screen-001/tradeoffs-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-001/tradeoffs-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| tradeoffs-s2 | [C0](../../runs/exploration-20260922/screen-001/tradeoffs-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-001/tradeoffs-s2/C_001.md) | 0 | Submitted unchanged; stopped |
| authored-s1 | [C0](../../runs/exploration-20260922/screen-001/authored-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-001/authored-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| authored-s2 | [C0](../../runs/exploration-20260922/screen-001/authored-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-001/authored-s2/C_001.md) | 0 | Submitted unchanged; stopped |

### Review after considering self-generated examples

Run folder: `screen-002`.

| Trajectory | Saved constitutions in order | Edited reviews | Outcome |
|---|---|---:|---|
| polished-s1 | [C0](../../runs/exploration-20260922/screen-002/polished-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-002/polished-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| polished-s2 | [C0](../../runs/exploration-20260922/screen-002/polished-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-002/polished-s2/C_001.md) | 0 | Submitted unchanged; stopped |
| practical-s1 | [C0](../../runs/exploration-20260922/screen-002/practical-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-002/practical-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| practical-s2 | [C0](../../runs/exploration-20260922/screen-002/practical-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-002/practical-s2/C_001.md) | 0 | Submitted unchanged; stopped |
| sparse-s1 | [C0](../../runs/exploration-20260922/screen-002/sparse-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-002/sparse-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| sparse-s2 | [C0](../../runs/exploration-20260922/screen-002/sparse-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-002/sparse-s2/C_001.md) | 0 | Submitted unchanged; stopped |
| tradeoffs-s1 | [C0](../../runs/exploration-20260922/screen-002/tradeoffs-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-002/tradeoffs-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| tradeoffs-s2 | [C0](../../runs/exploration-20260922/screen-002/tradeoffs-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-002/tradeoffs-s2/C_001.md) | 0 | Submitted unchanged; stopped |
| authored-s1 | [C0](../../runs/exploration-20260922/screen-002/authored-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-002/authored-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| authored-s2 | [C0](../../runs/exploration-20260922/screen-002/authored-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-002/authored-s2/C_001.md) | 0 | Submitted unchanged; stopped |

### Review using three fixed practical dilemmas

Run folder: `screen-003`.

| Trajectory | Saved constitutions in order | Edited reviews | Outcome |
|---|---|---:|---|
| practical-s1 | [C0](../../runs/exploration-20260922/screen-003/practical-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-003/practical-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| practical-s2 | [C0](../../runs/exploration-20260922/screen-003/practical-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-003/practical-s2/C_001.md) | 0 | Submitted unchanged; stopped |
| sparse-s1 | [C0](../../runs/exploration-20260922/screen-003/sparse-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-003/sparse-s1/C_001.md) → [C2](../../runs/exploration-20260922/screen-003/sparse-s1/C_002.md) | 1 | Submitted unchanged; stopped |
| sparse-s2 | [C0](../../runs/exploration-20260922/screen-003/sparse-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-003/sparse-s2/C_001.md) | 0 | Submitted unchanged; stopped |
| agency-s1 | [C0](../../runs/exploration-20260922/screen-003/agency-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-003/agency-s1/C_001.md) → [C2](../../runs/exploration-20260922/screen-003/agency-s1/C_002.md) | 1 | Submitted unchanged; stopped |
| agency-s2 | [C0](../../runs/exploration-20260922/screen-003/agency-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-003/agency-s2/C_001.md) | 0 | Submitted unchanged; stopped |
| care-s1 | [C0](../../runs/exploration-20260922/screen-003/care-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-003/care-s1/C_001.md) → [C2](../../runs/exploration-20260922/screen-003/care-s1/C_002.md) | 1 | Submitted unchanged; stopped |
| care-s2 | [C0](../../runs/exploration-20260922/screen-003/care-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-003/care-s2/C_001.md) → [C2](../../runs/exploration-20260922/screen-003/care-s2/C_002.md) | 1 | Submitted unchanged; stopped |

### Review with competing agency/care alternatives

Run folder: `screen-004`.

| Trajectory | Saved constitutions in order | Edited reviews | Outcome |
|---|---|---:|---|
| agency-s1 | [C0](../../runs/exploration-20260922/screen-004/agency-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-004/agency-s1/C_001.md) → [C2](../../runs/exploration-20260922/screen-004/agency-s1/C_002.md) → [C3](../../runs/exploration-20260922/screen-004/agency-s1/C_003.md) → [C4](../../runs/exploration-20260922/screen-004/agency-s1/C_004.md) → [C5](../../runs/exploration-20260922/screen-004/agency-s1/C_005.md) → [C6](../../runs/exploration-20260922/screen-004/agency-s1/C_006.md) | 5 | Submitted unchanged; stopped |
| agency-s2 | [C0](../../runs/exploration-20260922/screen-004/agency-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-004/agency-s2/C_001.md) | 0 | Submitted unchanged; stopped |
| care-s1 | [C0](../../runs/exploration-20260922/screen-004/care-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-004/care-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| care-s2 | [C0](../../runs/exploration-20260922/screen-004/care-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-004/care-s2/C_001.md) → [C2](../../runs/exploration-20260922/screen-004/care-s2/C_002.md) | 1 | Submitted unchanged; stopped |

### Earlier trained checkpoint reviewing the short drafts

Run folder: `screen-005`.

| Trajectory | Saved constitutions in order | Edited reviews | Outcome |
|---|---|---:|---|
| sparse-s1 | [C0](../../runs/exploration-20260922/screen-005/sparse-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-005/sparse-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| sparse-s2 | [C0](../../runs/exploration-20260922/screen-005/sparse-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-005/sparse-s2/C_001.md) | 0 | Submitted unchanged; stopped |
| care-s1 | [C0](../../runs/exploration-20260922/screen-005/care-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-005/care-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| care-s2 | [C0](../../runs/exploration-20260922/screen-005/care-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-005/care-s2/C_001.md) | 0 | Submitted unchanged; stopped |

### Thinking-mode appraisal, initial settings

Run folder: `screen-006`.

| Trajectory | Saved constitutions in order | Edited reviews | Outcome |
|---|---|---:|---|
| sparse-s1 | [C0](../../runs/exploration-20260922/screen-006/sparse-s1/C_000.md) | 0 | Review failed; not convergence |
| sparse-s2 | [C0](../../runs/exploration-20260922/screen-006/sparse-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-006/sparse-s2/C_001.md) | 0 | Submitted unchanged; stopped |
| care-s1 | [C0](../../runs/exploration-20260922/screen-006/care-s1/C_000.md) | 0 | Review failed; not convergence |
| care-s2 | [C0](../../runs/exploration-20260922/screen-006/care-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-006/care-s2/C_001.md) | 0 | Submitted unchanged; stopped |

### Thinking-mode appraisal, recommended settings

Run folder: `screen-007`.

| Trajectory | Saved constitutions in order | Edited reviews | Outcome |
|---|---|---:|---|
| sparse-s1 | [C0](../../runs/exploration-20260922/screen-007/sparse-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-007/sparse-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| sparse-s2 | [C0](../../runs/exploration-20260922/screen-007/sparse-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-007/sparse-s2/C_001.md) | 0 | Submitted unchanged; stopped |

### Competing alternatives with greedy decoding

Run folder: `screen-008`.

| Trajectory | Saved constitutions in order | Edited reviews | Outcome |
|---|---|---:|---|
| agency-s1 | [C0](../../runs/exploration-20260922/screen-008/agency-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-008/agency-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| agency-s2 | [C0](../../runs/exploration-20260922/screen-008/agency-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-008/agency-s2/C_001.md) | 0 | Submitted unchanged; stopped |
| care-s1 | [C0](../../runs/exploration-20260922/screen-008/care-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-008/care-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| care-s2 | [C0](../../runs/exploration-20260922/screen-008/care-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-008/care-s2/C_001.md) → [C2](../../runs/exploration-20260922/screen-008/care-s2/C_002.md) | 1 | Submitted unchanged; stopped |

### Fixed practical dilemmas with native tool calls

Run folder: `screen-009`.

| Trajectory | Saved constitutions in order | Edited reviews | Outcome |
|---|---|---:|---|
| sparse-s1 | [C0](../../runs/exploration-20260922/screen-009/sparse-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-009/sparse-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| sparse-s2 | [C0](../../runs/exploration-20260922/screen-009/sparse-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-009/sparse-s2/C_001.md) → [C2](../../runs/exploration-20260922/screen-009/sparse-s2/C_002.md) → [C3](../../runs/exploration-20260922/screen-009/sparse-s2/C_003.md) → [C4](../../runs/exploration-20260922/screen-009/sparse-s2/C_004.md) → [C5](../../runs/exploration-20260922/screen-009/sparse-s2/C_005.md) | 4 | Submitted unchanged; stopped |
| care-s1 | [C0](../../runs/exploration-20260922/screen-009/care-s1/C_000.md) → [C1](../../runs/exploration-20260922/screen-009/care-s1/C_001.md) | 0 | Submitted unchanged; stopped |
| care-s2 | [C0](../../runs/exploration-20260922/screen-009/care-s2/C_000.md) → [C1](../../runs/exploration-20260922/screen-009/care-s2/C_001.md) | 0 | Submitted unchanged; stopped |

### Training comparison: original model, JSON commands

Run folder: `paired-before`.

| Trajectory | Saved constitutions in order | Edited reviews | Outcome |
|---|---|---:|---|
| s1 | [C0](../../runs/exploration-20260922/paired-before/s1/C_000.md) → [C1](../../runs/exploration-20260922/paired-before/s1/C_001.md) | 0 | Submitted unchanged; stopped |
| s2 | [C0](../../runs/exploration-20260922/paired-before/s2/C_000.md) → [C1](../../runs/exploration-20260922/paired-before/s2/C_001.md) | 0 | Submitted unchanged; stopped |

### Training comparison: trained model, JSON commands

Run folder: `paired-after`.

| Trajectory | Saved constitutions in order | Edited reviews | Outcome |
|---|---|---:|---|
| s1 | [C0](../../runs/exploration-20260922/paired-after/s1/C_000.md) → [C1](../../runs/exploration-20260922/paired-after/s1/C_001.md) | 0 | Submitted unchanged; stopped |
| s2 | [C0](../../runs/exploration-20260922/paired-after/s2/C_000.md) → [C1](../../runs/exploration-20260922/paired-after/s2/C_001.md) | 0 | Submitted unchanged; stopped |

### Training comparison: original model, native tool calls

Run folder: `paired-native-before`.

| Trajectory | Saved constitutions in order | Edited reviews | Outcome |
|---|---|---:|---|
| s1 | [C0](../../runs/exploration-20260922/paired-native-before/s1/C_000.md) → [C1](../../runs/exploration-20260922/paired-native-before/s1/C_001.md) → [C2](../../runs/exploration-20260922/paired-native-before/s1/C_002.md) | 1 | Submitted unchanged; stopped |
| s2 | [C0](../../runs/exploration-20260922/paired-native-before/s2/C_000.md) → [C1](../../runs/exploration-20260922/paired-native-before/s2/C_001.md) | 0 | Submitted unchanged; stopped |

### Training comparison: trained model, native tool calls

Run folder: `paired-native-after`.

| Trajectory | Saved constitutions in order | Edited reviews | Outcome |
|---|---|---:|---|
| s1 | [C0](../../runs/exploration-20260922/paired-native-after/s1/C_000.md) → [C1](../../runs/exploration-20260922/paired-native-after/s1/C_001.md) | 0 | Submitted unchanged; stopped |
| s2 | [C0](../../runs/exploration-20260922/paired-native-after/s2/C_000.md) → [C1](../../runs/exploration-20260922/paired-native-after/s2/C_001.md) → [C2](../../runs/exploration-20260922/paired-native-after/s2/C_002.md) → [C3](../../runs/exploration-20260922/paired-native-after/s2/C_003.md) | 2 | Submitted unchanged; stopped |

Every trajectory directory also contains `review_001`, `review_002`, etc. Those folders contain `constitution.diff`, the public appraisal, decision summaries, and tool events. The links above cover submitted constitutions; a proposal written in an appraisal is not necessarily the text that was submitted.
