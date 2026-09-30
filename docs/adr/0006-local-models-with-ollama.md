# 0006 — Ollama locally, fakes in tests

**Decision.** `llama3.2:3b` + `nomic-embed-text` served by Ollama on the host (a 6 GB GPU is plenty);
`FakeChat` / `HashingEmbeddings` (deterministic, report token usage, stream) for tests; one
provider factory (`rag/providers.py`).

**Alternatives.** A hosted model API from day one (costs per experiment, needs a key) ·
llama.cpp directly (more setup).

**Consequences.** + Free unlimited load tests; latency and TTFC are real and interesting on a
laptop GPU. + CI never calls a model. − A 3B model answers worse than a hosted one; quality metrics
are relative. The `obslab.llm.cost.usd` metric shows what the same traffic would cost on an API.
