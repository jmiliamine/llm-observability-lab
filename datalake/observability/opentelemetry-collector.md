# The OpenTelemetry Collector

The collector is a process that receives telemetry, transforms it and sends it on. Applications export OTLP to the collector instead of talking to each backend directly.

A pipeline has three kinds of components:

- **Receivers** accept data: `otlp` (gRPC on 4317, HTTP on 4318), `prometheus` (scrapes targets), `filelog` (tails files).
- **Processors** change it: `batch` groups data before export, `memory_limiter` refuses data before the process runs out of memory, `k8sattributes` adds pod, namespace and deployment names, `attributes` and `transform` edit or drop fields.
- **Exporters** send it: `otlp` to Tempo, `prometheusremotewrite` or `prometheus` for metrics, `otlphttp` to Loki.

Pipelines are declared per signal:

    service:
      pipelines:
        traces:  {receivers: [otlp], processors: [memory_limiter, batch], exporters: [otlp/tempo]}
        metrics: {receivers: [otlp], processors: [memory_limiter, batch], exporters: [prometheus]}
        logs:    {receivers: [otlp], processors: [memory_limiter, batch], exporters: [otlphttp/loki]}

Why keep a collector in the middle:

- The app only knows one endpoint. Switching Tempo for another backend is a collector change, not a code change.
- Retries and buffering happen outside the app process.
- Sensitive attributes can be removed in one place.
- Kubernetes metadata is added from the API, which the app does not need to call.

`memory_limiter` must come first in the processor list and `batch` last. The collector exposes its own metrics (`otelcol_exporter_send_failed_spans` and friends), which is how you notice it dropping data.
