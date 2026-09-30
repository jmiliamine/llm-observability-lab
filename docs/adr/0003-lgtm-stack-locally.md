# 0003 — Explicit LGTM services

**Decision.** Separate Prometheus, Tempo, Loki, Grafana and Collector, each with its own config
file, dashboards and datasources provisioned as code (Docker Compose, then Kubernetes in 0009).

**Alternatives.** `grafana/otel-lgtm` all-in-one image (one container, zero config, but every
setting is hidden) · Grafana Cloud free tier (no control over storage and retention) ·
Elastic / SigNoz (capable products with their own data models).

**Consequences.** + Every setting (retention, exemplars, OTLP in Loki, spanmetrics) is visible and
explainable. + The same files map to managed services. − ~1.5 GB RAM; on Windows, Docker Desktop
needs WSL2 (Virtual Machine Platform enabled).
