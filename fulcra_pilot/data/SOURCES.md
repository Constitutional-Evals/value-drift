# OCT constitution inputs

Downloaded 2026-11-03 from Jinzhou Wu's published Hugging Face model repository.
Only constitution text was downloaded; no model or adapter weights were needed.

- `oct_broad/C_000.md`: https://huggingface.co/JinzhouWu/value-drift-oct-adapters/blob/main/qwen3.8-27b/broad/C_000.md
- `oct_broad/C_001.md`: https://huggingface.co/JinzhouWu/value-drift-oct-adapters/blob/main/qwen3.8-27b/broad/round_001/C_001.md
- `oct_broad/C_002.md`: https://huggingface.co/JinzhouWu/value-drift-oct-adapters/blob/main/qwen3.8-27b/broad/round_002/C_002.md

The API runner records exact text and SHA-256 hashes in its manifest. These files were fetched
from `main`, not a pinned source revision. A version name identifies a document, not a model
checkpoint: editing C_001 into C_002 and training on C_002 are separate steps.
