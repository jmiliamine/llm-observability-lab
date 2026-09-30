# Changelog

## 0.1.0 (unreleased)

First public version.

- LangGraph RAG (`retrieve → generate → grade`, one rewrite, fallback) served by FastAPI.
- OpenTelemetry traces, metrics and logs named after the GenAI semantic conventions.
- k3d cluster with kube-prometheus-stack, Tempo, Loki, the OpenTelemetry Collector and
  Traefik as the Gateway API implementation, from pinned Helm charts.
- Generated Grafana dashboard, SLO recording rules and burn-rate alerts, shared with a
  Docker Compose version of the stack.
- `fake` overlay: the whole lab without Ollama or a GPU.
- PostgreSQL + pgvector vector store: read-only role for the API, atomic re-index, index
  metadata checked against the configured embedding model, statement timeouts, network policy.
  Two API replicas with a PodDisruptionBudget.
- Sample notes, input and error guardrails.
- Tests: unit and integration (offline), pgvector, stack, cluster and real-model end-to-end suites.
