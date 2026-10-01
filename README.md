# llm-observability-lab

[![CI](https://github.com/jmiliamine/llm-observability-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/jmiliamine/llm-observability-lab/actions/workflows/ci.yml)

A RAG over your own notes, built with LangGraph, instrumented with the
[OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/),
and observed with Prometheus, Tempo, Loki and Grafana. The notes are searched with pgvector.
Everything runs in a two-node k3d cluster set up like a small company platform: Gateway API,
pinned Helm charts, restricted pods, SLO alerts.

![Grafana dashboard of the RAG: request rate, latency percentiles, tokens, retrieval scores](docs/img/dashboard.png)

Most LLM demos stop at the answer. This lab is about what happens around it. For every
question you can see how long each step took, how many tokens it used, why it ended in
"I don't know", and which pod served it. The same trace ID links the metric, the trace and the log line.

## What is in the box

- **The app.** A LangGraph flow: `retrieve → generate → grade`, with one query rewrite
  before giving up. Served by FastAPI (two replicas), local models through Ollama.
- **The vector store.** PostgreSQL with pgvector. The API connects with a read-only role,
  and the ingest job rebuilds the index and swaps it in atomically. An index built with another
  embedding model is refused.
- **The telemetry.** One trace per question, from the HTTP request down to each model call,
  named after the GenAI conventions (`chat llama3.2:3b`, `gen_ai.client.operation.duration`...).
  Prompts stay off the traces unless you opt in.

  ![One question as a trace in Tempo: the HTTP request, the LangGraph nodes, the embedding call and the llama3.2:3b call](docs/img/trace.png)
- **The platform.** kube-prometheus-stack, Tempo, Loki and the OpenTelemetry Collector
  from pinned Helm charts, Traefik as the Gateway API implementation, a local image registry.
- **The operations side.** SLO recording rules and alerts,
  a dashboard generated from code, liveness and readiness probes that answer different
  questions.

## Architecture

![A question goes through the Gateway to the RAG API. The API searches the pgvector index in PostgreSQL, calls Ollama for embeddings and answers, and sends traces, metrics and logs to the OpenTelemetry Collector, which forwards them to Tempo, Loki and Prometheus. Grafana reads all three.](docs/img/architecture.svg)

More detail, including what each namespace owns and how a request is traced, in
[docs/architecture.md](docs/architecture.md).

## Quick start

Tested on Windows 10 with Docker Desktop. Linux and macOS should work (every command
goes through [Task](https://taskfile.dev)), but have not been tested yet.

You need Docker Desktop with about **10 GB of memory** for its VM, and these tools:

```bash
winget install Docker.DockerDesktop Task.Task k3d.k3d Kubernetes.kubectl Helm.Helm astral-sh.uv
```

Ollama is optional. Without it, the lab runs with built-in fake models (see below).

```bash
winget install Ollama.Ollama
```

```bash
ollama pull llama3.2:3b
```

```bash
ollama pull nomic-embed-text
```

Then, from the repository:

```bash
task doctor
```

```bash
task setup
```

```bash
task up
```

`task up` takes about 15 minutes the first time: it creates the cluster, installs the
platform, builds the image with the notes in `samples/notes`, starts PostgreSQL, indexes the
notes into it and deploys the API.
No GPU or no Ollama? Use `task up OVERLAY=fake` instead. Everything is the same except the
answers, which become extracts of the notes instead of generated text.

Send some traffic and open Grafana:

```bash
task load
```

| What | Where |
|---|---|
| Ask a question | `task ask Q="How do taints and tolerations work?"` |
| Grafana | http://grafana.localhost:8080 (user `admin`, password from `task grafana:password`) |
| Prometheus | http://prometheus.localhost:8080 |

The dashboard is in the *LLM Observability* folder. Click a point on a latency panel to jump
to an example trace (exemplars), then from a span to its logs.

`task stop` pauses the cluster and gives the memory back; `task start` resumes it with all
its data. `task cluster:down` deletes it.

## Your own notes

Any folder of `.md` or `.txt` files works:

```bash
task app NOTES=D:/path/to/notes
```

This rebuilds the image with those notes and re-indexes them. The API keeps answering from the
previous index until the new one is complete. The notes end up inside a local image and a local
database only. Nothing leaves your machine, since the models run locally too.

## Lighter option: Docker Compose

If you only want the observability stack and PostgreSQL (about 1.5 GB instead of 4 GB) with
the app running on your machine:

```bash
task stack:up
```

```bash
task stack:ingest
```

Grafana is then on http://localhost:3000, PostgreSQL on `localhost:5432`, and the app exports
to `localhost:4318`, like in the cluster. `task stack:down` stops it.

## Tests

The first three run in CI on every push. Details in [tests/README.md](tests/README.md).

| Command | What it proves | Needs |
|---|---|---|
| `task test` | The graph, the telemetry (in-memory exporters), the API, the sample corpus, input and error guardrails. Outbound network is blocked. | nothing |
| `task test:pgvector` | Same ranking as the in-memory store, read-only API role, atomic re-index, model mismatch refused, query timeout | Docker (starts PostgreSQL) |
| `task lint` | Ruff, generated files in sync, both Kustomize overlays render | kubectl |
| `task test:compose` | Starts the Compose stack, indexes the sample notes, then follows one question: answer, metrics in Prometheus, full trace in Tempo (SQL span included), log line in Loki | Docker |
| `task test:stack` | The same telemetry checks against the cluster's platform | the cluster |
| `task test:k8s` | Through the Gateway: answer from pgvector, both replicas serving, pod identity on the trace, clean metric labels, SLO rules evaluated | the cluster |
| `task test:ollama` | The real models answer from the right note, and off-topic questions still fall back | Ollama |

## Layout

Each folder has its own README.

```
src/obslab/      the app: RAG graph, models, vector store, telemetry, API, CLI
tests/           unit, integration and end-to-end suites
deploy/k8s/      the cluster: k3d definition, platform (Helm values), app (Kustomize)
deploy/compose/  the same backends with Docker Compose
deploy/shared/   alert rules, dashboard and database setup used by both
samples/         the demo notes
scripts/         helpers behind the Task commands
docs/            architecture and troubleshooting
```

## Limits

- One PostgreSQL instance, no replication and no scheduled backups. Fine for a lab.
- Local use only. The UIs have no TLS, and anonymous access in the Compose stack is read-only.
- A 3B model answers like a 3B model. The point is the telemetry around it, not the answers.

Having trouble? See [docs/troubleshooting.md](docs/troubleshooting.md).

## License

MIT, see [LICENSE](LICENSE). The models are not part of this repository and have their own
licenses: Llama 3.2 (Llama 3.2 Community License) and nomic-embed-text (Apache 2.0).
