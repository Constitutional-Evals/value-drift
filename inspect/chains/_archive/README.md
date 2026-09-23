# Archived chain runs

Pilots, not results. These validated the driver and the experimental design before the
main run; they are kept for provenance and are skipped by `scripts/check_docs.py`.

- **`pilot`** — 2 chains, 3 rounds, Sonnet 5, at `authority=full_authority`. The first
  end-to-end test of `scripts/run_chain.py`: that round 1 splits epochs into chains, that
  rounds 2+ seed from each chain's own output, and that lineage verification holds.

- **`pilot-pref`** — the same 2 chains and 3 rounds at `authority=preferred_self`, run to
  compare the two framings on identical input before committing to one. The main run uses
  `preferred_self`.

Neither is large enough to support a claim. For results see
[`results/chains-main.md`](../../results/chains-main.md).
