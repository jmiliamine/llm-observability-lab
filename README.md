# llm-observability-lab

[![CI](https://github.com/jmiliamine/llm-observability-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/jmiliamine/llm-observability-lab/actions/workflows/ci.yml)

A small question-answering app over a folder of notes, built to be watched. Every question
leaves a trace, metrics and a log line, and the whole thing runs on a local Kubernetes cluster
with Prometheus, Tempo, Loki and Grafana.

![Grafana dashboard: request rate, latency percentiles, time to first chunk, tokens](docs/img/dashboard.png)

## What it does

You give it a folder of Markdown or text notes. It cuts them into chunks, turns each chunk into
a vector with an embedding model, and stores the vectors in PostgreSQL (pgvector).

When you ask a question, it embeds the question the same way, fetches the closest chunks, and
hands them to a small language model with one instruction: answer from this text only. If
nothing in the notes is close enough, it rewrites the question once and tries again. If that
fails too, it says "I don't know" instead of making something up.

That is retrieval-augmented generation (RAG) in its smallest useful form. The models run
locally through [Ollama](https://ollama.com) (`llama3.2:3b` and `nomic-embed-text`), so the notes
never leave the machine.

## Why it is built around observability

An LLM app can return HTTP 200 and still be broken: the first word takes eight seconds, token
usage doubles after a prompt change, retrieval quietly finds nothing, or the answer has little
to do with the retrieved text. None of that shows up in a status code.

So the app is instrumented with OpenTelemetry, using the
[GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) for names,
and each question can be followed end to end:

![One question as a trace: HTTP request, graph nodes, embedding call, SQL query, model call](docs/img/trace.png)

With that in place, these become things you look up rather than guess:

- Where did the 4.7 seconds go? In the trace above: 86 ms to retrieve (18 ms of it in
  PostgreSQL) and 4.6 s in the model.
- How long until the first word, and how many tokens per answer? What would this traffic cost
  on a paid API?
- How often does retrieval find nothing relevant? A rising "I don't know" ratio after a
  deployment usually means the index and the embedding model no longer match.
- Are we within the latency objective? Recording rules and burn-rate alerts answer that.
- Which pod served this request, and what did it log? The trace ID is on the span, on the
  metric sample and on the log line, so Grafana jumps from one to the other.

Prompts and answers are kept out of the telemetry unless you switch that on.

## How it is put together

![The request goes through the Gateway to the API, which searches PostgreSQL and calls Ollama. Telemetry goes to the Collector, then Tempo, Loki and Prometheus; Grafana reads all three.](docs/img/architecture.svg)

The cluster is k3d (k3s in Docker) with two nodes, split the way a small company would split
it. The platform side holds the monitoring stack and the Gateway, installed from pinned Helm
charts. The app side holds the API (two replicas), PostgreSQL and the indexing job, as plain
manifests with Kustomize. More in [docs/architecture.md](docs/architecture.md).

## Try it

Tested on Windows 10 with Docker Desktop. Every command goes through
[Task](https://taskfile.dev), and CI runs the tests on Linux; the cluster itself has not been
tried on Linux or macOS yet.

You need Docker Desktop with about 10 GB of memory, and a few tools:

```bash
winget install Docker.DockerDesktop Task.Task k3d.k3d Kubernetes.kubectl Helm.Helm astral-sh.uv
```

Ollama is optional. Without it, use the `fake` mode below.

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

`task up` takes 15 to 25 minutes the first time, mostly image downloads. It creates the
cluster, installs the platform, builds the app image with the sample notes, indexes them and
deploys the API. No GPU or no Ollama? `task up OVERLAY=fake` runs the same thing with built-in
fake models: the answers become extracts of the notes, and all the telemetry still flows.

Ask something, then send some traffic so the dashboards have data:

```bash
task ask Q="How do taints and tolerations work?"
```

```bash
task load
```

Grafana is at http://grafana.localhost:8080 (user `admin`, password from
`task grafana:password`), with the dashboard in the *LLM Observability* folder. Click a point on
a latency panel to open the matching trace, and from a span, its logs.

`task stop` pauses the cluster and gives the memory back, `task start` brings it back, and
`task cluster:down` deletes it.

### Your own notes

```bash
task app NOTES=/path/to/your/notes
```

This rebuilds the image with that folder and re-indexes it. The API keeps answering from the
previous index until the new one is complete.

### Without the cluster

For a lighter setup (about 1.5 GB), the same backends run with Docker Compose and the app runs
on your machine:

```bash
task stack:up
```

Grafana is then at http://localhost:3000. See [src/obslab](src/obslab/README.md) for how to
index and ask from there.

## Tests

`task test` runs in a couple of seconds with no network: fake models, telemetry captured in
memory. Beyond that, each level needs a bit more and proves a bit more:

| Command | What it proves |
|---|---|
| `task test` | the graph, its spans and metrics, the API, input and error handling |
| `task test:pgvector` | the vector store against a real PostgreSQL: read-only API role, atomic re-index, timeouts |
| `task test:compose` | one question followed through the Compose stack: answer, metrics, full trace, log line |
| `task test:k8s` | the same through the cluster's Gateway, with both replicas and the alert rules |
| `task test:ollama` | the real models answer from the right note |

The first three run in CI on every push. Details in [tests/README.md](tests/README.md).

## Where things are

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

It is a lab. One PostgreSQL instance without replication or backups, plain HTTP on
`*.localhost`, and a 3B model that answers like a 3B model. The interesting part is what you can
see around the answers, not the answers themselves.

If something does not start, see [docs/troubleshooting.md](docs/troubleshooting.md).

## License

MIT, see [LICENSE](LICENSE). The models are not part of this repository and have their own
licenses: Llama 3.2 (Llama 3.2 Community License) and nomic-embed-text (Apache 2.0).
