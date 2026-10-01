# Metric cardinality

Every unique combination of metric name and label values is a separate time series. Prometheus keeps recent series in memory, so the number of series, not the number of samples, is what costs RAM.

Low cardinality labels have a small, known set of values: HTTP method, status code class, route template, model name, region. High cardinality labels grow without limit: user IDs, request IDs, trace IDs, full URLs with query strings, raw question text, timestamps.

One high cardinality label multiplies everything else. A histogram with 12 buckets, 5 routes and 3 status classes is 180 series. Add a `user_id` label with 10,000 users and it is 1.8 million.

Rules that hold up:

- Put identifiers on spans and logs, not on metrics. A trace can carry the question text if content capture is enabled; a metric never should.
- Use the route template (`/users/{id}`) instead of the path.
- Bucket continuous values before they become labels.
- Watch out for labels added for you. Kubernetes attribute processors can attach pod UIDs and start times, which change on every restart and create new series each time.

To find the culprits, query `topk(10, count by (__name__)({__name__=~".+"}))` for the metrics with the most series, and the TSDB status page in the Prometheus UI for the labels with the most values.

Exemplars are the escape hatch: a histogram bucket can carry a trace ID as an exemplar without it becoming a label, so you jump from a slow bucket to one slow trace.
