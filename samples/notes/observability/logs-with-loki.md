# Logs with Loki

Loki indexes labels, not log content. A stream is identified by its label set, for example `{service_name="rag-api", namespace="rag"}`, and the lines inside a stream are compressed chunks searched at query time.

This makes Loki cheap to run, as long as labels stay low cardinality. The same rule as for metrics applies: a trace ID or a user ID as a label creates one stream per value and hurts ingestion and queries. Loki 3 has **structured metadata** for this: per-line key-value pairs that are stored with the line but not indexed. OTLP log attributes such as `trace_id` land there.

A LogQL query selects streams, then filters lines:

    {service_name="rag-api"} |= "timeout" | json | duration > 5s

- `|=` and `!=` filter on text, `|~` on a regular expression.
- `| json` or `| logfmt` parse the line into fields.
- Filters on structured metadata work like filters on parsed fields: `| trace_id="4bf92f..."`.

Metric queries turn logs into time series: `sum by (level) (count_over_time({service_name="rag-api"}[5m]))`.

Retention is set globally or per tenant. On a single node with the filesystem store, keep it short and put a size limit on the volume.

In Grafana, a derived field or the Tempo data source configuration links a `trace_id` in a log line to the trace, which is the fastest path from "an error was logged" to "this is what the request did".
