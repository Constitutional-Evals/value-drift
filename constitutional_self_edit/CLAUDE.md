@AGENTS.md

# Obsidian Knowledge Graph — SPAR

A durable, interlinked knowledge base for the SPAR value-drift research on the `obsidian` MCP
server, **written for agents first**. Read it to inform your work; write to it when you reach a new
decision/discovery. Its value is the hard-won, non-obvious knowledge — negative results, traps,
confounds, judge/rater artifacts, pipeline pitfalls — that is expensive to rediscover. Rules marked
**(hard)** are binding.

## Read first (hard)
- Before any non-trivial task (launching or planning a run, editing prompts/configs/constitutions,
  analysing results, writing a report, interpreting model behaviour), **search `SPAR/` and read the
  matching notes.** Orient from the [[SPAR]] MOC + its decision index.
- **Always** check [[Reproducibility Gotchas]] before running/trusting an experiment, and check for a
  `*Confound*`/`*Artifact*`/`*Negative Result*` note before designing a comparison or claiming an
  effect. Rediscovering a documented trap (e.g. drift that is really rater noise, a judge that prefers
  longer documents) is a failure to use the graph.
- Treat a relevant note as a primary source: cite it to the user by title and reconcile your
  findings with it (correcting it per **Keep notes true** if they conflict).
- **Ground every behavioural claim in raw outputs, not only in aggregates (hard).** A judge score,
  axis rating, edit-size metric or embedding distance is a *proxy*; it is **not** the model's values.
  Before claiming a model "drifted toward X", "preserved itself", or "converged", read a sample of the
  actual submitted constitutions/diffs/transcripts behind the number and say what they show. Before
  comparing across studies, check that the review prompt, starting constitution, word cap, judge model
  and noise floor match (see `reports/` and `configs/`).
- **When the graph is silent on a fact, consult the primary source before asserting (hard)** — the
  study report in `reports/`, the config in `configs/`, the code, or the cited paper (e.g. Open
  Character Training, arXiv 2511.01689). A report or paper cited but not distilled into a note is
  *not* "in the graph"; if you had to open it to answer, fold the fact back into a note that same turn.
- `runs/`, `checkpoints/` and the prompt banks are local-only and often absent on this machine; say so
  rather than inventing their contents. Collaborators' results may arrive as claude.ai artifact links
  before they are committed — record the link in `source:`.
- If the server is unreachable (Obsidian closed), **say so** and proceed without the graph — don't
  silently skip it or assume it's empty.

## Scope (hard)
- Only create/edit notes inside `SPAR/`. Do not read or write anything outside.
- **`SPAR/` is a folder in the Obsidian vault, reached ONLY through the `obsidian` MCP server
  (`mcp__obsidian__vault_write`/`vault_read`/`vault_patch`/…). It is NOT a path in this repo.**

## Verify before you rely (hard)
Every note has `status:` — `unverified` (checked by no one but its author), `verified`
(independently checked), or `superseded`. A fresh note is **always** `unverified`.

Every note has a `## How to verify` block, and **the check must be able to fail the way that
note-type is wrong.** Governing principle: reproduction only catches a wrong *number* — a verifier
re-running the author's pipeline inherits the author's bug (wrong prompt variant, leaked context,
mis-joined judge ratings, wrong denominator). Match the check to the failure mode:

| type | how it's wrong | procedure |
|---|---|---|
| `experiment`, result-bearing `concept` | the number or its interpretation | **audit the backing script, config and a sample of raw outputs against the claim** — right prompt/config, right model ids, correct filtering and denominators, noise floor applied, judge blind to condition — **without re-running it.** Re-run only when the run is cheap and free (offline analysis over existing outputs, seconds–minutes) or the audit surfaces a specific suspicion; then give exact command, expected values + tolerance, falsifier, runtime. **Never re-run a paid API batch or GPU training run as the default check.** |
| `method` | the procedure | **invariants** checkable *independently of the implementation* (e.g. "the reviewer never sees the previous diff", "submitted constitution ≤ word cap", "DPO chosen = teacher, rejected = student"). Never restate the code — a faithful transcription of a bug reads as correct. Assert invariants in `tests/` where practical. |
| definitional `concept` | the definition/scope | a worked case with a known answer, plus a case it must *exclude* (e.g. what counts as a "substantive edit" vs. a rewording) |
| `paper` | attribution | resolve the citation, check the claim against the source with section/quote |
| `question` | stale (silently answered) | check `status:` of the notes it depends on |
| `moc` | coverage | every link resolves; every in-scope note reachable (no orphans) |

- **The author never verifies their own result** — leave it `unverified`, flag it, keep building
  freely. Verification is a *future, independent* agent's job.
- **The first *later* agent to rely on an `unverified` result must independently audit it**
  first (not re-read). "Rely on" = cite as established, build on, or justify a decision. (Relying
  only on results you wrote this session triggers nothing.)
- **Audit, don't re-execute (hard).** "Verify" here means *check the agent's reasoning and that the
  script is written correctly* — not reproduce the number. A verifier who re-runs the author's
  pipeline inherits the author's bug, so a clean reproduction is near-zero evidence about the failure
  mode that matters. Read the script against the note's claims; check the prompts and configs it used,
  that conditions are compared on matched settings, that the judge/rater noise floor is accounted for,
  and spot-check raw outputs. Paid re-runs are **not** a verification step.
- **Verification is independent:** spawn a *separate* subagent whose only inputs are the note's
  `## How to verify` block + the referenced code/outputs — not your reasoning or the writer's narrative.
- **Compute and API spend are gated on user approval (hard).** Anything that costs money or GPU time —
  OpenRouter/Anthropic/OpenAI calls (reviews, judging, rating, embeddings), training, generation,
  evaluation, a RunPod/H200 job — must not launch unprompted. Follow `AGENTS.md`: state the full scale
  (conditions × reps × rounds, judging volume, total) and, each time, on separate lines: a **cost +
  time estimate**, a **≤2-sentence summary of what's being run**, and a **≤2-sentence summary of what
  it aims to show**. Re-state this fresh right before launch even if discussed earlier. Until an
  approved run happens, a result that has not been computed does not exist — never present a projected
  or assumed number as measured. (A run that *did* happen but is `unverified` is gold — see below.)
- **Exempt from the gate (run freely, no approval):** pure inspection (reading code, configs, raw
  outputs, resolving a citation), the CPU test suite (`pytest tests`), offline analysis/plotting over
  outputs already on disk that makes no API calls, and read-only graph/repo consistency tooling.
- **On success:** set `status: verified`, add `verified_by` + `verified` (date), append a `## History`
  line. **On failure:** don't silently fix — set `superseded` (or keep `unverified` with a dated
  `## History` note), tell the user, treat as untrusted.
- **Verification is one-time:** once `verified`, trust it — don't re-run. **Exception (staleness):**
  if `code:` or the referenced config/prompt was modified *after* the `verified` date, treat as
  `unverified` again (note in `## History`) and re-verify once.
- **`unverified` means "the reasoning has not been audited" — NOT "the number is in doubt."** Logged
  outputs of a run are what the run produced; what verification protects against is mistakes in
  design, analysis or interpretation. **Treat `unverified` run outputs as gold** — quote them as
  results, put them in reports without hedging, build on them. Mention the status only when it is
  decision-relevant (e.g. proposing an audit, or a live interpretation concern) — not as a reflexive
  disclaimer. Sampling noise is a separate matter: report it via $N$, CIs and noise floors.

## Cascade invalidation (hard)
`depends_on:` lists the notes a note rests on (direct only; walked transitively).
- **When a note is corrected/superseded, walk its backlinks + `depends_on:` in the same turn** and
  mark every dependent: `status: unverified`/`superseded`, a `## History` line naming the upstream
  change, and a top-of-body flag of what's now in doubt vs unaffected.
- **State the blast radius explicitly:** which results are void, which provisional, which untouched
  *and why*. Both an over-broad retraction and silence are failures.
- A dependent is *provisional* not void when the upstream error is common-mode across the comparison
  it makes (e.g. a judge bias that hits every arm equally leaves a between-arm difference intact) —
  say which case applies and why.

## Graph shape: atomic nodes, DAG not tree (hard)
- **DAG, not tree** — a note may have multiple parents. Keep two structures separate: the
  `depends_on:` DAG (load-bearing, for verification + cascade) and navigation (`type: moc` hubs +
  decision index, holds no claims).
- **One claim per node** — one result/method/concept, one `status:`, one `## How to verify`. If parts
  verify *differently* (e.g. a measured edit rate + an interpretation of why models edit), **split
  into two nodes** joined by a `depends_on:` edge. Never paper over mixed verification with a
  "verified (scoped)" caveat.
- **`depends_on:` is the single source of truth for edges**, "builds on" direction only. Never
  hand-maintain the reverse (derived from backlinks). A prose `[[link]]` is fine, but the dependency
  lives only in `depends_on:`.
- **An edge means "rests on", not "mentions"** — add one only if this note's claim would be in doubt
  were the target wrong. Otherwise use a body `[[link]]` and no edge.

## Keep notes true (hard)
- **On discovering anything that contradicts a note, fix the note that same turn** — don't just tell
  the user. Includes code/config/prompt/report changes: update every note describing the old state.
- **Fold the correction into the body so the top is always current truth**; record why-it-was-wrong +
  date in `## History`. Never leave a stale claim standing with a contradicting addendum below — an
  agent reading top-down (or truncating) ingests the wrong claim first.

## Agent-first notes (hard)
Assume the reader is an agent under a tight context budget who may read only the first screenful.
- **Bottom line at the very top:** the first body line (after the H1) is a `> ` blockquote —
  **≤3 sentences / ~50 words**, stating claim + status + effect size and nothing else. If it needs
  more, that's the signal the note holds more than one claim — **split it**.
- **Top = current state, never chronology.** Corrections are edited into the relevant section; the
  dated reversal log lives in `## History`.
- **If answering a question the note is about required reading code or outputs, fold that answer
  back into the note the same turn** — a fact you had to look up belongs in the note.
- **One canonical claim, one owner note** — others `[[link]]` to it, never restate it. Merge/demote
  duplicates.
- **Claims carry numbers (hard):** state the effect size, not the direction. Not "blind review
  elicits more edits" but "blind values-first review produced substantive edits in 146/156 first
  reviews (26 models × 6 reps) vs. … under the standard prompt". Include magnitude, $N$ (models,
  seeds, chains, reviews), paired-or-not, CI or test statistic, judge/rater model and noise floor,
  and regime (prompt variant, starting constitution, word cap, model ids) — whatever applies, in
  `claim:` and wherever the body asserts a comparison. A bare direction can't be re-evaluated when
  something upstream changes.
- **Atomic** — one concept/paper/method/result/question per note. **Title = the concept** in Title
  Case (`Blind Values-First Review`), stable (it's the `[[wikilink]]` target).

Frontmatter for every note:
```yaml
---
type: concept        # concept | paper | method | experiment | question | moc
tags: []
created: 2026-10-22  # today's date; don't guess
source:              # arXiv id, DOI, URL, report path, artifact link, or "conversation"
aliases: []          # alternate names so links resolve
depends_on: []       # note titles this rests on (see Cascade invalidation)
status:              # unverified | verified | superseded — ALL notes
verified:            # date the independent check passed (omit until then)
verified_by:         # who/what ran the check (omit until then)
# --- results only (experiment, or a concept asserting a numeric fact) ---
claim:               # bottom line in one line, WITH effect size and N
code:                # exact repo path(s) of the runner/analysis script(s)
config:              # exact config/plan path(s) and prompt variant
runs:                # run/batch ids (e.g. runs/full-011, batch prompt-screen); note if local-only
models:              # model ids, incl. judge/rater
cost:                # API $ and/or GPU hours actually spent
---
```

## Code ↔ graph bridge (hard)
- **Every result note names the exact script, config and run ids** that produced it — in the
  frontmatter and `## How to verify`. The path, not "the analysis script".
- **Every backing script carries a top pointer comment** listing the `SPAR/<Note Title>` notes it
  supports, spelled exactly (a stale pointer is a broken bridge).
- **[[Project File Map]] is the index of this bridge — keep it current the same turn** you add/move/
  rename a script, config or result note.
- The graph complements `reports/`, it doesn't replace it: reports are the human-facing narrative,
  notes are the atomic, verifiable claims. Link each result note to the report section that presents
  it, and keep the two consistent.

## Growing the graph
- **Write without asking (hard)** — never ask the user whether to record something in the graph or
  offer to "write it up". Whenever you learn something a future agent would find useful (a result, an
  interpretation, a trap, a correction, an answer you had to dig for), record it in the same turn, then
  mention in one line what you recorded. Paid runs still need approval; notes never do.
- **Search first** — extend/correct an existing note, never create a near-duplicate.
- **Link generously**; no orphans (link to ≥1 note, be linked from ≥1). Linking to a not-yet-existing
  note is fine but **create at least a stub** for it.
- Maintain **MOCs** (`type: moc`) as per-topic hubs of `[[links]]` (e.g. per study, per pipeline
  stage). The root [[SPAR]] MOC carries the **decision index** ("about to do X → read Y first") — keep
  it current.
- If [[SPAR]], [[Reproducibility Gotchas]] or [[Project File Map]] doesn't exist yet, create it (as
  `unverified`, seeded from `README.md` and `reports/`) the first time you need it.

## Voice
Durable knowledge for a future agent, not a chat log. State claims plainly, cite `source`, mark
anything uncertain/unverified and set `status` accordingly.
