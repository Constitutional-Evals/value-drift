# Starting constitutions (C0 seeds)

**These files are researcher-constructed research instruments. They are not validated
statements of universal human values, and they are not "neutral", no normative document
is. They are called *broad-consensus* and *minimal* to describe their construction, not
to assert correctness.**

This README is documentation for researchers. **It is never shown to the subject model.**
Only the `.md` seed file itself is copied into the sandbox, as `/workspace/constitution.md`.

## Seeds

| File | Words | Role | Committed? |
|---|---|---|---|
| `c0_general_assistant.md` | ~545 | Recursive-chain seed (Experiment 4) | yes |
| `c0_broad_consensus.md` | ~480 | Default seed / reference cell | yes |
| `c0_minimal.md` | ~87 | Sparse contrast: lots of headroom to add | yes |
| `c0_eb_universal_kindness.md` | ~655 | Value-loaded: impartial-care anchor | **no, fetched** |
| `c0_eb_conservatism.md` | ~591 | Value-loaded: tradition/continuity anchor | **no, fetched** |
| `c0_eb_marxism.md` | ~787 | Value-loaded: historical-materialist anchor | **no, fetched** |

The three `c0_eb_*` seeds are **not committed**. Regenerate them with:

```bash
python scripts/fetch_eigenbench_seeds.py
```

### `c0_general_assistant.md`

Fifteen principles, written as the seed for the recursive self-authorship chains. It
shares the design properties of `c0_broad_consensus.md` with one deliberate exception:
it **does** pre-install the oversight and anti-power-seeking content that
`c0_broad_consensus.md` omits, in P14.

That inversion is the point. In the recursive setting the question is not whether a
model spontaneously writes itself a corrigibility clause, but whether an existing one
**survives** repeated self-authorship. A seed without P14 cannot measure erosion,
because there is nothing to erode.

Consequence for measurement: the `added_oversight` detector in `content.py` is
uninformative on this seed, since the topic is present in C0. Per-principle survival
and weakening must be tracked instead.

### `c0_broad_consensus.md`

Twelve principles chosen to satisfy the design properties in
`docs/experiment1_inspect_build_spec.md` §2:

1. Provider-neutral, no "Claude", "OpenAI", "Anthropic", no principal hierarchy.
2. Plausible and broadly defensible, the model is not forced to repair absurd content.
3. Short enough that individual edits stay legible.
4. Broad rather than exhaustive, room for models to add principles we did not pre-install.
5. Contains natural tradeoffs (helpfulness vs. harm, autonomy vs. third-party effects,
   pluralism vs. truth) so priority-setting behaviour is observable.
6. Does **not** pre-answer the interesting questions: no self-preservation,
   anti-self-preservation, power-seeking, shutdown, or provider-loyalty clauses.
7. No global priority ordering, the document explicitly declines to rank its principles,
   so introducing a hierarchy is an observable model choice.

Its ideas are grounded in several public source families, none copied verbatim:

- Anthropic, *Claude's Constitution* (2023) and *Claude's Constitution* (2026)
- Anthropic + Collective Intelligence Project, *Collective Constitutional AI* (the
  75-principle public constitution; strongest published broad-consensus source bank)
- OpenAI, *Model Spec*
- UN *Universal Declaration of Human Rights*
- Kundu et al., *Specific versus General Principles for Constitutional AI* (arXiv:2310.13798)

Full URLs are in `docs/experiment1_inspect_build_spec.md` §15.

### `c0_minimal.md`

A deliberately sparse four-principle seed in the same register and voice as the
broad-consensus seed. It exists to test whether models fill a vacuum: it omits
epistemics, pluralism, third-party effects, corrigibility, role honesty, and
proportionality, all of which the broad-consensus seed states explicitly.

Because voice, framing, and the closing "not ranked / use judgment" clause are held
constant across both seeds, **document length and coverage are close to the only
difference** between them.

## The EigenBench-derived seeds (`c0_eb_*`)

Derived from the **EigenBench provisional anchor constitutions**
([Constitutional-Evals/constitutions](https://github.com/Constitutional-Evals/constitutions),
`Provisional Constitutions/Provisional Anchors/`), pinned to commit `c3d994e`.

**Upstream is not a constitution.** Each file is a judge rubric: JSON with an `overview`,
12 `criteria`, and 5 `guidelines`, where every criterion/guideline carries a `comparative`
statement, a `reasoning` justification with scholarly citations, and **two `scenarios`,
which are evaluation prompts**. The converter keeps the overview and the 17 `comparative`
statements as numbered principles and discards the rest.

Dropping `scenarios` is not a stylistic choice. Those are eval prompts; a subject that
read them would know it was being evaluated, and every condition in the study would be
contaminated. `fetch_eigenbench_seeds.py` asserts none of them survive into the output.

### Known limitations of the conversion

- **No closing paragraph.** `c0_broad_consensus` ends with "These principles are
  deliberately not given a fixed global priority order", our sentence, not upstream's.
  Writing it into the Marxism seed would put a substantive claim in that value system's
  mouth, so these seeds have no equivalent clause. **Consequence: the "model introduces a
  priority ordering" finding from run 1 is not directly comparable across seed families**,
  because only `c0_*` seeds contain a statement to override.
- **The title is generic** (identical to c0) rather than naming the value system. The
  overview paragraph carries the orientation; a branded title would add a cue c0 lacks.
- **Form still differs from c0.** c0's principles have bold titles (`1. **Be honest.**`);
  these are untitled sentences, because inventing titles would be authoring normative
  content. Seed comparisons therefore vary in form as well as content.

### Licensing

The upstream repository carries **no license file** (`NOASSERTION`). The derived `.md`
files are gitignored and fetched per checkout rather than redistributed here. Before
publishing anything built on them, check with the upstream authors.

## Adding a seed

Drop a `.md` file in this directory and pass `-T seed=<filename stem>`. Seeds are
discovered by filesystem scan; no code change is needed. Document its provenance here.

Planned later seeds (see build spec §13, *not* implemented in v1):
an untouched published constitution, a provider-specific spec, a deliberately
self-contradictory seed, and a strongly value-loaded / persona seed.

## Versioning

Every run records the SHA-256 of the exact C0 bytes it was given. If you edit a seed
file, previous logs remain interpretable via that hash, but prefer adding a new file
over mutating an existing one.
