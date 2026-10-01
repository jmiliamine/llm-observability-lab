# Tests

Five levels, from "runs anywhere in two seconds" to "needs the whole cluster". Each level is one
Task command, and each one needs a bit more than the previous.

| Level | Command | Needs | Runs in CI |
|---|---|---|---|
| Unit and integration | `task test` | nothing (fake models, in-memory exporters, no network) | every push |
| Vector store | `task test:pgvector` | Docker | every push |
| Compose end to end | `task test:compose` | Docker | every push |
| Cluster end to end | `task test:k8s`, `task test:stack` | the k3d cluster (`task up`) | not yet |
| Real models | `task test:ollama` | Ollama with both models pulled | no |

## What each level checks

**Unit and integration** (`unit/`, `integration/`). The RAG graph and its branches, the spans and
metrics it emits, the HTTP API, the sample notes against the load-test questions, input limits
and error messages. The telemetry is captured in memory, so the tests can assert on exact span
names and attributes.

**Vector store** (`e2e/test_pgvector.py`). The pgvector store against a real PostgreSQL: same
ranking as the in-memory store, a read-only API role, a re-index that readers never see half
done, an index from another embedding model refused, slow queries cut off, a pool that recovers
after the database drops its connections.

**Data lake** (`e2e/test_datalake.py`, same command). Runs the real `obslab ingest` on a copy of
the sample notes: a note added to the folder is answered after the next ingest, a removed note
is forgotten, files that are not `.md` or `.txt` are ignored, and an empty or missing folder
fails without touching the index that is being served.

**Compose end to end** (`e2e/test_stack.py`). Starts Prometheus, Tempo, Loki, Grafana, the
OpenTelemetry Collector and PostgreSQL with Docker Compose, indexes the sample notes, then asks
one question and follows it:

1. the answer comes from the right note,
2. its metrics are in Prometheus,
3. its trace is complete in Tempo, down to the SQL query on `rag.chunks`,
4. its log line is in Loki, findable by trace ID.

This is the cheapest test that proves the whole telemetry path, and it needs no model: the app
runs with the fake provider.

**Cluster end to end** (`e2e/test_cluster.py`, plus `test_stack.py` against the cluster). The
same question through the Gateway: both API replicas answer, the trace carries the pod
identity, metric labels stay bounded, the SLO rules are evaluated. A note added to the data lake
is served after the ingest job, with the same image and the same API pods, and only that job
mounts the folder.

**Real models** (`e2e/test_ollama.py`). With `llama3.2:3b` and `nomic-embed-text`: a question
about the notes is answered from the right note, an off-topic question is declined.

## Conventions

- Tests that need infrastructure carry a marker (`pgvector`, `stack`, `k8s`, `ollama`) and are
  deselected by default; the Task commands select them.
- When a Task command runs them, a missing dependency is a failure, not a skip
  (`OBSLAB_REQUIRE_STACK=1`). Run `pytest -m stack` by hand and they skip instead.
- `conftest.py` holds the shared fixtures: fake models, a three-document corpus, in-memory
  span and metric exporters.
