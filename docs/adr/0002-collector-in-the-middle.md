# 0002 — The app only talks OTLP to a Collector

**Context.** Metrics go to Prometheus, traces to Tempo, logs to Loki; in a cloud account they
would go to managed equivalents.

**Decision.** The app exports everything over OTLP/HTTP to `localhost:4318`. The OpenTelemetry
Collector routes, batches, limits memory, derives RED metrics from spans (`spanmetrics`
connector) and exposes metrics to Prometheus.

**Alternatives.** App exposes `/metrics` for Prometheus + sends traces directly to Tempo
(two protocols in the app, backend-specific code) · push straight to Grafana Cloud.

**Consequences.** + Changing backends = swapping Collector exporters, zero app
change. + Central place for sampling, PII redaction, attribute filtering. − One more moving
part; its health check (`:13133`) is part of the stack test.
