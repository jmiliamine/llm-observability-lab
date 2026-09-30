# Architecture Decision Records

Each record: context, decision, alternatives weighed, consequences. Short on purpose:
one screen, one decision.

| # | Decision | Status |
|---|---|---|
| [0001](0001-otel-as-the-instrumentation-standard.md) | OpenTelemetry + GenAI semantic conventions, no vendor SDK | Accepted |
| [0002](0002-collector-in-the-middle.md) | App talks OTLP to a Collector only; backends are the Collector's business | Accepted |
| [0003](0003-lgtm-stack-locally.md) | Prometheus + Tempo + Loki + Grafana, explicit services (not the all-in-one image) | Accepted — now on Kubernetes (0009), compose kept (0014) |
| [0004](0004-langgraph-for-the-rag-flow.md) | LangGraph state machine instead of a single LCEL chain | Accepted |
| [0005](0005-own-callback-instrumentation.md) | Hand-written LangChain callback → OTel instead of auto-instrumentation | Accepted |
| [0006](0006-local-models-with-ollama.md) | Ollama locally, fakes in tests, one provider factory | Accepted |
| [0007](0007-cardinality-and-content-policy.md) | Bounded metric labels; prompt/answer capture opt-in on spans only | Accepted |
| [0008](0008-pgvector-vector-store.md) | PostgreSQL + pgvector as the vector store, with its guardrails | Accepted |
| [0009](0009-k3d-for-the-home-lab-cluster.md) | k3d (k3s) cluster instead of VirtualBox VMs, minikube or kind | Accepted |
| [0010](0010-platform-as-pinned-helm-charts.md) | Platform = pinned Helm charts + Taskfile; GitOps with the CI/CD decision | Accepted |
| [0011](0011-gateway-api-instead-of-ingress.md) | Gateway API on Traefik instead of Ingress (ingress-nginx EOL) | Accepted |
| [0012](0012-workload-security-baseline.md) | Restricted PSS, least-privilege database roles, requests without CPU limits | Accepted |
| [0013](0013-ollama-outside-the-cluster.md) | Ollama on the host behind an ExternalName Service | Accepted |
| [0014](0014-compose-kept-as-fallback.md) | Compose kept as a fallback on the same shared config | Accepted |
| [0015](0015-no-gpu-mode-with-fakes.md) | A no-GPU mode: deterministic fake models, end to end | Accepted |
