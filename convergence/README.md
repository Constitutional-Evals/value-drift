# convergence

Code for evaluating constitutional drift, implementing metrics from
Lionel's working notes ("Metrics on constitutions", 2026-09-09):

- **metric 1** — `cos(C, C') := cosine similarity between e(C) and e(C')`,
  for a fixed text embedding `e`. Cheap, no LLM inference required.
- **metric 2** — `K(C||C') := E_s[d_KL(M(.|C,s) || M(.|C',s))]`, the KL
  divergence between what a model M does when prompted with C vs C'.
  Behavioral, but asymmetric and dependent on the choice of M. **This
  implementation is a next-token approximation evaluated at a single
  fixed prompt, not the scenario-averaged full formula** — see
  `convergence/metrics/kl.py`'s module docstring for exactly what that
  means and why.

Metrics 3-6 (KL between character-trained models, EigenBench Procrustes
distance, the ridge-regression logical-equivalence metric, and detection)
are not yet implemented — see "Design notes" below.

## Layout

```
convergence/
  constitutions.py     Constitution: an ordered, immutable list of criteria
  embeddings.py         Embedder protocol + OpenAI / OpenRouter / Voyage / local backends + cache
  prompted_models.py    PromptedModel protocol + ChatLogprobModel (OpenAI/OpenRouter via logprobs)
  metrics/
    cosine.py             cosine_similarity() and CosineSimilarityMetric      (metric 1)
    kl.py                  next_token_kl_divergence() and PromptedKLMetric    (metric 2, next-token approx.)
scripts/
  compare_constitutions.py       CLI: metric 1 between two constitutions from JSON files
  compare_constitutions_kl.py    CLI: metric 2 (next-token KL) between two constitutions
examples/
  C.json, C_prime.json           sample constitutions for the CLI
  metta_v1.json, metta_v2.json,
  metta_t0.json, metta_t1.json   real constitutions compared during development
tests/
  fake_embedder.py, fake_prompted_model.py    deterministic offline stand-ins used only in tests
  test_constitutions.py, test_cosine.py, test_embeddings.py, test_kl.py, test_prompted_models.py
```

## Install

```
pip install -e .              # core (numpy only)
pip install -e ".[openai]"    # + openai client, for OpenAIEmbedder / ChatLogprobModel
pip install -e ".[openrouter]" # + openai client, for OpenRouter (OpenAI-compatible)
pip install -e ".[voyage]"    # + voyageai client, for VoyageEmbedder
pip install -e ".[local]"     # + sentence-transformers, for a local no-API-key embedder
pip install -e ".[dev]"       # + pytest, to run the test suite
```

## Metric 1: cosine similarity

Embeddings require an API key — this code never needs your key directly,
it just reads it from your environment at runtime:

```
export OPENAI_API_KEY=sk-...
python scripts/compare_constitutions.py examples/C.json examples/C_prime.json
```

To use Voyage instead of OpenAI:

```
export VOYAGE_API_KEY=...
export CONVERGENCE_EMBEDDING_PROVIDER=voyage
python scripts/compare_constitutions.py examples/C.json examples/C_prime.json
```

### Using OpenRouter

[OpenRouter](https://openrouter.ai) exposes an OpenAI-compatible
embeddings endpoint (`https://openrouter.ai/api/v1/embeddings`), so no
separate client library is needed — `OpenAIEmbedder` is just pointed at
OpenRouter's base URL instead of OpenAI's. Install the `openai` package
(`pip install -e ".[openrouter]"`), then:

```
export OPENROUTER_API_KEY=sk-or-...
export CONVERGENCE_EMBEDDING_PROVIDER=openrouter
python scripts/compare_constitutions.py examples/C.json examples/C_prime.json
```

Model names on OpenRouter are namespaced by underlying provider, e.g.
`openai/text-embedding-3-small` (the default), `qwen/qwen3-embedding-8b`,
or `voyageai/voyage-4` — see
[OpenRouter's embedding model list](https://openrouter.ai/docs/api_reference/embeddings)
for the current options. Override the default with:

```
export CONVERGENCE_EMBEDDING_MODEL=qwen/qwen3-embedding-8b
```

Or from Python directly, without going through `get_default_embedder()`:

```python
from convergence.embeddings import OpenRouterEmbedder
from convergence.metrics.cosine import CosineSimilarityMetric

embedder = OpenRouterEmbedder(model="openai/text-embedding-3-small")  # reads OPENROUTER_API_KEY
metric = CosineSimilarityMetric(embedder)
```

Embeddings are cached in `.embedding_cache.json` (gitignored) keyed by
`(provider, model, text)`, so re-comparing the same constitutions never
re-issues an API call.

### Per-criterion similarity

`cos(C, C')` above joins every criterion into one blob before embedding,
which gives a single aggregate number. To instead see where two
constitutions agree or diverge criterion-by-criterion (e.g. comparing a
revision that's meant to preserve the same structure, like
`metta_t0.json` vs `metta_t1.json`), pass `--per-criterion`:

```
python scripts/compare_constitutions.py examples/metta_t0.json examples/metta_t1.json --per-criterion
```

This embeds `C_i` and `C'_i` separately for each index `i` and prints:

```
Per-criterion similarity:

0.9123  I embody compassion, generosity, and goodwill in how I respond.

0.8842  I consider the impacts of my words on all potentially affected parties.

...
```

Requires both constitutions to have the same number of criteria, paired
by position. From Python: `CosineSimilarityMetric.per_criterion(c1, c2)`
returns `[(criterion_text, score), ...]`.

### No API access? Use a local model

If every embedding API is unreachable (e.g. a sandboxed environment
whose network policy blocks them), `LocalEmbedder` runs a
sentence-transformers model with no key and no network access at call
time (weights download once from Hugging Face on first use):

```
pip install -e ".[local]"
export CONVERGENCE_EMBEDDING_PROVIDER=local
python scripts/compare_constitutions.py examples/C.json examples/C_prime.json
```

Embedding quality is lower than OpenAI/Voyage/OpenRouter's hosted
models, so treat results as a rough signal, not a final number.

### Using it as a library

```python
from convergence.constitutions import Constitution
from convergence.embeddings import get_default_embedder
from convergence.metrics.cosine import CosineSimilarityMetric

c1 = Constitution(["Be helpful.", "Be honest."], name="C")
c2 = Constitution(["Assist users.", "Never lie."], name="C'")

metric = CosineSimilarityMetric(get_default_embedder())
print(metric(c1, c2))

# Or compare many constitutions at once (one embedding call per
# constitution, not one per pair):
matrix = metric.pairwise_matrix([c1, c2, ...])
```

## Metric 2: KL between prompted models (next-token approximation, single fixed prompt)

`K(C||C')` in the notes is a KL divergence between two full *response*
distributions, averaged over a scenario distribution S. Neither is
computed exactly here: what's implemented is (a) the KL divergence
between the two *next-token* distributions only (the model's
distribution over the first token of its reply) — tractable via the
`logprobs`/`top_logprobs` chat completions parameter, but blind to
divergence that only shows up later in a response — evaluated at (b) a
single fixed, neutral user message instead of an expectation over a
scenario set. Read `convergence/metrics/kl.py`'s module docstring before
trusting a number from this — it explains exactly what's being
approximated and how.

```
export OPENAI_API_KEY=sk-...
python scripts/compare_constitutions_kl.py examples/metta_t0.json examples/metta_t1.json
```

Or via OpenRouter (defaults to an OpenAI-hosted model routed through it,
since OpenAI's logprobs support is the most reliable — other models'
support varies by provider and isn't guaranteed):

```
export OPENROUTER_API_KEY=sk-or-...
export CONVERGENCE_KL_PROVIDER=openrouter
python scripts/compare_constitutions_kl.py examples/metta_t0.json examples/metta_t1.json
```

The fixed user message defaults to `PromptedKLMetric.DEFAULT_USER_MESSAGE`
("How should you respond?"); override it with `--user-message` on the
CLI, or the `user_message=` argument in Python.

```python
from convergence.constitutions import Constitution
from convergence.prompted_models import get_default_prompted_model
from convergence.metrics.kl import PromptedKLMetric

model = get_default_prompted_model()  # reads OPENAI_API_KEY or OPENROUTER_API_KEY
metric = PromptedKLMetric(model)

c1 = Constitution.from_json_file("examples/metta_t0.json")
c2 = Constitution.from_json_file("examples/metta_t1.json")

print(metric(c1, c2))              # K(c1 || c2)
print(metric(c2, c1))              # K(c2 || c1) -- NOT the same value, KL is asymmetric
print(metric.symmetrized(c1, c2))  # 0.5 * (K(c1||c2) + K(c2||c1)), if you want one number
```

## Design notes / open questions carried over from Lionel's notes

- **Text rendering matters.** `Constitution.to_text()` joins criteria
  with blank lines by default. The notes flag metric 1 as "sensitive to
  formatting, syntax, style" — the ridge-regression discussion (metric
  5) goes further and argues that *how a constitution is split into
  criteria* can itself carry information EigenBench and OCT are
  sensitive to. `CosineSimilarityMetric(text_joiner=...)` and
  `Constitution.to_text(joiner=...)` are exposed as explicit knobs
  rather than a hardcoded choice, so this can be experimented with
  directly rather than papered over.
- **e is swappable, deliberately.** `embeddings.Embedder` is a small
  protocol (just `.embed(texts) -> vectors`), so adding a third
  provider, or swapping in a fine-tuned/domain-specific embedding
  model, doesn't touch `metrics/cosine.py`.
- **Metric 2 here is next-token, not full-response.** The notes' K(C||C')
  is a KL divergence over entire response distributions. A faithful
  Monte Carlo estimate of that needs teacher-forced logprobs for an
  arbitrarily supplied continuation under two different prompts, which
  most hosted chat APIs don't expose (only for tokens they themselves
  generated) — typically requiring a local open-weight model instead,
  which is presumably why the notes call out "open-weight language
  model M" as a dependency. What's built here is the cheaper, tractable
  proxy: KL over just the first token. A sequence-level Monte Carlo
  estimator (sample full responses under C, score them under both C and
  C' via teacher-forced logprobs, average) is a natural next build, and
  a distinct implementation from this one, not a fix to it.
- **The scenario expectation is dropped, not approximated.** Lionel's
  notes define K(C||C') as an expectation over a scenario distribution
  S; this implementation evaluates at a single fixed user message
  instead (see `PromptedKLMetric.DEFAULT_USER_MESSAGE`), which is a
  further simplification beyond the next-token approximation, not a
  stand-in for S — see `convergence/metrics/kl.py`'s module docstring.
- **The M dependence isn't mitigated yet.** The notes suggest averaging
  metric 2 over a few different choices of M to reduce model-specific
  noise; `PromptedKLMetric` runs against a single model per call, so
  averaging across models is currently a manual step (run it once per
  model, average the results yourself).
- **Top-k logprob truncation is a real approximation.** `next_token_kl_divergence`
  only ever sees the top_k tokens the API returns (default 20), not the
  full vocabulary distribution. It floors and renormalizes over the
  union of what both calls returned so KL stays finite, but this
  systematically undercounts tail probability mass the API never
  reports — see the docstring in `metrics/kl.py`.
- **Not yet implemented:** metrics 3-6 (KL between character-trained
  models, EigenBench Procrustes distance, the ridge-regression
  logical-equivalence metric, and the detection metric). Metric 3 needs
  actually running the character-training (OCT) fine-tune per
  constitution — expensive unless those fine-tunes already exist, per
  the notes. The `Constitution` type here is written generically enough
  that it should be reusable as the input type for those metrics too.

## Tests

```
pytest tests/ -v
```

All 45 tests currently pass using deterministic fake embedders/models
(plus, for the API-backend tests, object construction and stubbed
responses with dummy keys) — no real API key or network access is
needed to verify either metric's math (cosine identity/symmetry, KL
zero-for-identical/asymmetry/disjoint-support handling) or the provider
wiring (OpenAI / OpenRouter / Voyage base URLs, model IDs, missing-key
and missing-logprobs errors) independent of any real model's quality.
