# 0015 — A no-GPU mode: deterministic fake models, end to end

**Context.** The lab should run on any machine that has Docker, including one without a GPU or
without Ollama. Deterministic fake models (`FakeChat`, `HashingEmbeddings`) exist for the unit
tests.

**Decision.** The fakes are also a deployment option. `task up OVERLAY=fake` deploys the same
manifests with `OBSLAB_PROVIDER=fake` and a lower relevance threshold (0.2). The hashing
embeddings skip stop words and hash 1024 dimensions, which is enough for the sample notes: every
load-test question retrieves its note, off-topic questions fall back. The ingest job writes the
fake vectors to pgvector like real ones; the index metadata (ADR 0008) keeps an index built with
one model from being queried with the other.

**Alternatives.** A tiny real model on CPU (a download of several hundred MB, slow on a laptop,
still non-deterministic) · a mock HTTP server imitating the Ollama API (more code to maintain,
and it tests the mock rather than the app).

**Consequences.** + Anyone can see the whole pipeline (Gateway, database, traces, metrics, logs,
SLO rules) in about 15 minutes, and the e2e tests run in CI without a model. + A unit test pins
the contract between the sample notes and the load generator. − Fake answers are extracts of the
context, not generated text: latency and token numbers only mean something with a real model.
− Scores of the two embedding models are not comparable, hence one threshold per overlay.
