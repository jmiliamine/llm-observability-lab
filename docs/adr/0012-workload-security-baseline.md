# 0012 — Workload security and resource baseline

Applied to everything in the app namespace, checked by Pod Security Admission:

- Namespace `obslab` enforces the **restricted** Pod Security Standard, PostgreSQL included.
- Image: multi-stage, `python:3.14-slim-trixie`, non-root UID 10001, no build tools, OCI labels,
  immutable tag (git SHA or timestamp, never `latest`), pushed to a registry.
- Pods: `runAsNonRoot`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`, all
  capabilities dropped, `seccompProfile: RuntimeDefault`, no ServiceAccount token mounted.
  PostgreSQL runs as its image's `postgres` user (UID 999) and writes only to its volume, its
  socket directory and `/tmp`.
- Network: default-deny ingress; only the Gateway may reach the API, only the API and the ingest
  job may reach PostgreSQL (k3s enforces NetworkPolicy).
- Database: least privilege (read-only role for the API, writer role for the ingest job, the
  superuser only in the first-start script), statement timeouts; details in ADR 0008.
- Availability: two API replicas spread over the nodes, a PodDisruptionBudget, rolling updates
  that start a new pod before stopping an old one.
- Resources: requests on every container, memory limits as OOM guard, **no CPU limits**
  (throttling hurts latency even on an idle node; requests already share CPU fairly).
- Probes: liveness `/healthz` (the process), readiness `/readyz` (the app's own database holds a
  matching index). Readiness does not call Ollama: a shared model server being down must not
  empty the Service; it shows as errors and alerts instead.
- Config in a ConfigMap, secrets in Secrets (Grafana admin and database passwords generated at
  install time, never in git, never printed by the tasks).

Not done yet: egress NetworkPolicies, image signing (cosign) plus SBOM and scan in CI, admission
policies (Kyverno), external secrets, database backups.
