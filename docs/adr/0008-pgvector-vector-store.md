# 0008 — PostgreSQL + pgvector as the vector store

**Context.** The API needs a similarity search over a few thousand chunks, shared by several
replicas and rebuilt by a batch job while the API keeps serving.

**Decision.** PostgreSQL 18 with the pgvector extension, in the app namespace (a StatefulSet in
the cluster, a service in Compose). One table `rag.chunks` (text, source, metadata,
`vector(dim)`) with an HNSW index on cosine distance, and a one-row `rag.index_meta` table that
records the provider, embedding model, dimension and chunk count of the current index. The app
talks to it through a small `VectorStore` implementation (`src/obslab/rag/pgvector.py`, psycopg 3
and a connection pool), so the RAG graph is unchanged. An in-memory store (a JSON file) remains
for offline development and unit tests (`OBSLAB_VECTOR_STORE=memory`).

**Guardrails.**

| Risk | Guardrail | Checked by |
|---|---|---|
| The API alters or deletes the index | Two roles: `obslab_reader` (SELECT only, read-only transactions) for the API, `obslab_writer` for the ingest job | `test_the_api_role_cannot_change_anything` |
| Readers see a half-built index | Rebuild into `rag.chunks_build`, then swap tables and metadata in one short transaction | `test_readers_never_see_a_half_built_index` |
| Index and model do not match (vectors are not comparable) | Metadata table; `/readyz` returns 503 with the reason; queries with the wrong dimension fail with an explicit error | `test_an_index_from_another_model_is_refused_with_a_clear_message`, `test_readiness_reports_the_model_mismatch` |
| A database restart leaves dead connections in the pool | Each connection is checked before use and replaced if dead; idle ones are closed after 5 min | `test_the_pool_recovers_when_the_server_drops_connections` |
| A slow query holds a request | `statement_timeout` on every connection (5 s) and on the reader role, connect timeout 3 s | `test_slow_queries_are_cut_by_the_statement_timeout` |
| Unbounded or hostile input | `k` clamped to 1..20, question length 3..2000, parameterized SQL only, fixed table names | `test_k_is_bounded`, `test_question_text_is_never_sql` |
| Connection details leak to clients | Credentials only in libpq variables from a Secret; `/readyz` and 502 bodies carry the error type, not the message | `tests/unit/test_guardrails.py` |
| Other pods connect to the database | NetworkPolicy: only the API and ingest pods reach port 5432 | `postgres.yaml`, checked by hand (see below) |

The named tests run against a real PostgreSQL in `task test:pgvector`
(`tests/e2e/test_pgvector.py`), except `tests/unit/test_guardrails.py`, which runs offline in
`task test`. The NetworkPolicy is checked by hand: a pod in another namespace, or an unlabelled
pod in `obslab`, gets no answer on port 5432.

**Alternatives.** In-memory store loaded from a volume (no extra service, but one replica only
and a full reload on every change) · Chroma (another service with its own API) · OpenSearch
(heavier, better for hybrid keyword + vector search at scale) · a managed vector database (not
local).

**Consequences.** + The API is stateless: two replicas, a PodDisruptionBudget, rollouts without
downtime. + Re-indexing does not restart anything. + Standard SQL tooling for inspection and
backups. − One more stateful component to run and back up. − Scores of different embedding
models are not comparable: switching models means a full re-index (the metadata check enforces it).
