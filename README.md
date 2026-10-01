# llm-observability-lab

[![CI](https://github.com/jmiliamine/llm-observability-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/jmiliamine/llm-observability-lab/actions/workflows/ci.yml)

A RAG over a folder of notes, built with LangGraph, instrumented with the
[OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/),
and observed with Prometheus, Tempo, Loki and Grafana. It runs on a two-node k3d cluster laid
out like a small company platform: Gateway API, pinned Helm charts, restricted pods, SLO rules.

![Grafana dashboard: request rate, latency percentiles, time to first chunk, tokens](docs/img/dashboard.png)

## Stack

| Layer | What | Notes |
|---|---|---|
| App | Python 3.14, FastAPI, LangGraph 1.2 | 2 replicas, stateless |
| Models | Ollama: `llama3.2:3b` (chat), `nomic-embed-text` (embeddings, 768 dims) | on the host, behind an `ExternalName` Service; deterministic fakes for tests and CI |
| Vector store | PostgreSQL 18 + pgvector 0.8.6 | HNSW index, cosine distance |
| Instrumentation | OpenTelemetry SDK, OTLP/HTTP | GenAI conventions for model calls, DB conventions for SQL |
| Pipeline | OpenTelemetry Collector | `k8sattributes`, `spanmetrics`, label filtering |
| Backends | Prometheus (Operator), Tempo, Loki, Grafana | kube-prometheus-stack 91.5, Tempo 3.0, Loki 3.7 |
| Cluster | k3d, k3s v1.36, 1 server + 1 agent | Traefik as Gateway API implementation, local registry |
| Delivery | Helm (platform), Kustomize (app), Task | overlays `local` and `fake` |

## Request path

Ingest: every `.md`/`.txt` file is split with `RecursiveCharacterTextSplitter` (800 characters,
120 overlap), embedded, and written to `rag.chunks`. The rebuild happens in a staging table and
is swapped in one transaction.

Query (`POST /ask`), a LangGraph `StateGraph`:

```
retrieve ──► relevant chunks? ──yes──► generate ──► grade ──► answer
                 │ no
                 ▼
              rewrite (once) ──► retrieve ──► still nothing ──► fallback ("I don't know")
```

- `retrieve`: embed the question, `ORDER BY embedding <=> $1 LIMIT 4`, keep chunks with cosine
  similarity ≥ `OBSLAB_MIN_SCORE` (0.6 for `nomic-embed-text`).
- `rewrite`: the model reformulates the question as a search query, at most once.
- `generate`: streamed, so time to first chunk is measurable.
- `grade`: groundedness, the share of answer words found in the retrieved context.

## Telemetry

One trace per question, rooted at the HTTP server span:

![Trace in Tempo: POST /ask, invoke_workflow rag, rag.node retrieve, embeddings, SELECT rag.chunks, rag.node generate, chat llama3.2:3b](docs/img/trace.png)

| Signal | Names |
|---|---|
| Spans | `POST /ask` → `invoke_workflow rag` → `rag.node {retrieve,rewrite,generate,grade,fallback}` → `retrieval notes`, `embeddings {model}`, `SELECT rag.chunks`, `chat {model}` |
| GenAI metrics | `gen_ai.client.operation.duration`, `gen_ai.client.operation.time_to_first_chunk`, `gen_ai.client.inference.usage.{input,output}_tokens`, `gen_ai.invoke_workflow.duration` |
| RAG metrics | `rag.retrieval.top_score`, `rag.retrieval.relevant_documents`, `rag.query.rewrites`, `rag.fallbacks`, `rag.answer.groundedness`, `rag.graph.node.duration` |
| Cost | `obslab.llm.cost.usd`: what the same tokens would cost at a configurable API price |
| HTTP | `http.server.request.duration` (stable conventions) |
| Logs | one record per answer (route, rewrites, groundedness) over OTLP to Loki, with `trace_id` |

- **Correlation.** Histograms carry exemplars, so a latency point links to its trace; Tempo
  links a span to its Loki lines by trace ID.
- **Cardinality.** Metric attributes are bounded enums (operation, model, node, error type).
  The Collector strips per-pod identifiers that change on each rollout (`k8s.pod.uid`, start
  time, ReplicaSet uid) from metrics only; `k8s.pod.name` stays so replicas do not overwrite
  each other.
- **Content.** Prompts and answers are recorded on spans only with `OBSLAB_CAPTURE_CONTENT=true`.
- **Names in one place.** `src/obslab/telemetry/genai.py`. A hand-written LangChain callback
  handler (`telemetry/callbacks.py`, ~200 lines) maps framework events to spans and metrics.

Recording rules and alerts (`deploy/shared/prometheus/rag-slo.yml`, shipped as a
`PrometheusRule`):

| Rule | Alert |
|---|---|
| `rag:errors:ratio5m` | `RagErrorRateHigh` > 5% for 5 min |
| `rag:latency:p95_5m` | `RagLatencyP95High` > 30 s for 10 min |
| `rag:fallback:ratio15m` | `RagFallbackRateHigh` > 30% for 15 min |
| `rag:groundedness:p50_15m` | `RagGroundednessLow` < 0.5 for 15 min |
| `rag:requests:rate5m`, `rag:ttfc:p95_5m`, `llm:tokens:rate5m` | dashboard only |

The dashboard and the Kubernetes objects are generated from code
(`scripts/gen_observability.py`); CI fails if they drift.

## Architecture

![The request goes through the Gateway to the API, which searches PostgreSQL and calls Ollama. Telemetry goes to the Collector, then Tempo, Loki and Prometheus; Grafana reads all three.](docs/img/architecture.svg)

| Namespace | Owner | Contents |
|---|---|---|
| `monitoring` | platform | Prometheus Operator, Prometheus, Grafana, Alertmanager |
| `observability` | platform | OpenTelemetry Collector, Tempo, Loki |
| `gateway` | platform | one shared `Gateway` on `*.localhost`; apps attach `HTTPRoute`s |
| `obslab` | app | API, PostgreSQL, ingest CronJob, `HTTPRoute` |

The app also ships its alert rules (`PrometheusRule`) and its dashboard (a labelled `ConfigMap`),
which the Prometheus Operator and the Grafana sidecar pick up.

Workloads:

- Restricted Pod Security Standard on the app namespace, PostgreSQL included: non-root,
  read-only root filesystem, all capabilities dropped, no service account token.
- Requests on every container, memory limits, no CPU limits.
- Rolling updates with `maxUnavailable: 0`, a PodDisruptionBudget, topology spread over the nodes.
- Liveness `/healthz`. Readiness `/readyz` checks the database and the index, not Ollama.
- NetworkPolicies: only the Gateway reaches the API, only the API and the ingest job reach PostgreSQL.

Vector store:

- Two database roles: the API reads (`SELECT` only, read-only transactions), the ingest job writes.
- Index metadata records the embedding model and dimension; a mismatch returns 503 on `/readyz`.
- `statement_timeout` 5 s, `k` capped at 20, parameterized SQL, pooled connections checked
  before use (the API recovers by itself after a database restart).

More in [docs/architecture.md](docs/architecture.md), including the reasons behind each choice.

## Quick start

Tested on Windows 10 with Docker Desktop (about 10 GB for its VM). CI runs on Linux; the cluster
itself has not been tried on Linux or macOS.

```bash
winget install Docker.DockerDesktop Task.Task k3d.k3d Kubernetes.kubectl Helm.Helm astral-sh.uv
```

Optional, for real models (otherwise use `OVERLAY=fake`):

```bash
winget install Ollama.Ollama
```

```bash
ollama pull llama3.2:3b
```

```bash
ollama pull nomic-embed-text
```

Then:

```bash
task doctor
```

```bash
task setup
```

```bash
task up
```

`task up` creates the cluster, installs the platform, builds and pushes the image, starts
PostgreSQL, indexes `samples/notes` and rolls out the API: 15 to 25 minutes the first time,
mostly image pulls. `task up OVERLAY=fake` does the same without Ollama or a GPU.

```bash
task ask Q="How do taints and tolerations work?"
```

```bash
task load
```

| | |
|---|---|
| Grafana | http://grafana.localhost:8080 (`admin`, password from `task grafana:password`), folder *LLM Observability* |
| Prometheus | http://prometheus.localhost:8080 |
| Your own notes | `task app NOTES=/path/to/notes` (re-indexes without downtime) |
| Pause / resume | `task stop`, `task start` |
| Compose instead of the cluster | `task stack:up` (~1.5 GB, Grafana on http://localhost:3000) |

## Tests

| Command | Scope | CI |
|---|---|---|
| `task test` | graph branches, exact span tree and metric attributes (in-memory exporters), API, input and error handling; outbound network blocked | yes |
| `task test:pgvector` | real PostgreSQL: ranking parity with the in-memory store, read-only role, atomic re-index under a concurrent reader, model mismatch, statement timeout, pool recovery | yes |
| `task test:compose` | Compose stack: one question's answer, metrics in Prometheus, full trace in Tempo (SQL span included), log line in Loki | yes |
| `task test:k8s`, `task test:stack` | through the Gateway: both replicas serve, pod identity on the trace, bounded metric labels, rules evaluated | local |
| `task test:ollama` | real models answer from the right note, off-topic questions fall back | local |

Details in [tests/README.md](tests/README.md).

## Layout

Each folder has its own README.

```
src/obslab/      the app: RAG graph, models, vector store, telemetry, API, CLI
tests/           unit, integration and end-to-end suites
deploy/k8s/      k3d definition, platform (Helm values), app (Kustomize base + overlays)
deploy/compose/  the same backends with Docker Compose
deploy/shared/   alert rules, dashboard and database init used by both
samples/         the demo notes
scripts/         doctor, generators and build helpers behind the Task commands
docs/            architecture and troubleshooting
```

## Limits

- One PostgreSQL instance: no replication, no scheduled backups.
- Plain HTTP on `*.localhost`; local use only.
- Groundedness is a word-overlap proxy, not an LLM judge.
- A 3B model on a laptop GPU: latency and answer quality are what they are. The telemetry is the subject.

Troubleshooting: [docs/troubleshooting.md](docs/troubleshooting.md).

## License

MIT, see [LICENSE](LICENSE). The models are not part of this repository and have their own
licenses: Llama 3.2 (Llama 3.2 Community License) and nomic-embed-text (Apache 2.0).
