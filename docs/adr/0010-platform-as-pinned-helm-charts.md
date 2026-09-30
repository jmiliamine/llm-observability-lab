# 0010 — Platform components as pinned Helm charts, driven by Taskfile

**Decision.** kube-prometheus-stack 91.5.1 (Prometheus Operator), grafana-community/loki 18.13.5,
grafana-community/tempo 3.0.0, open-telemetry/opentelemetry-collector 0.173.1. One values file
per chart in `deploy/k8s/platform/values/`, versions pinned in `Taskfile.yml`, installed with
`helm upgrade --install --wait`. The app uses Kustomize (base + overlay), not a chart.

**Why.** Charts are how companies consume these components; pinning turns upgrades into a
reviewed one-line diff. The Operator makes scrape targets and alert rules Kubernetes objects
(ServiceMonitor, PrometheusRule) that each team ships next to its app. In 2026 Grafana moved its
community charts (Loki, Tempo) to `grafana-community/helm-charts`; the old `grafana/tempo` chart
is deprecated, hence the new repository.

**Alternatives.** Hand-written manifests (full control, no upgrade path) · Helmfile (declarative,
one more tool) · GitOps right away (Argo CD / Flux): the target, decided together with the CI/CD
platform (GitHub Actions or GitLab).

**Consequences.** + `task platform:up` is idempotent and reproducible. − Imperative `helm upgrade`
until GitOps lands: drift is possible if someone edits the cluster by hand.
