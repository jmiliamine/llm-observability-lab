# Histograms and percentiles

An average latency hides the requests people complain about. Percentiles show them: p50 is the typical request, p95 and p99 are the slow tail.

Prometheus computes percentiles from histograms. A histogram metric exposes cumulative buckets (`_bucket{le="0.5"}` counts requests that took at most 0.5 seconds), a `_count` and a `_sum`. The p95 over five minutes:

    histogram_quantile(0.95,
      sum by (le) (rate(http_server_request_duration_seconds_bucket[5m])))

Always aggregate with `sum by (le)` before `histogram_quantile`, and never average percentiles across instances. The average of two p95 values is not the p95 of the combined traffic.

The result is an estimate. It is interpolated inside a bucket, so its precision depends on the bucket boundaries. For an LLM call that takes between 1 and 30 seconds, default HTTP buckets (5 ms to 10 s) are useless at the top end. OpenTelemetry lets you set explicit bucket boundaries per instrument, and the GenAI conventions recommend some for token counts and durations.

Native histograms (exponential buckets) remove most of this tuning. They are supported by recent Prometheus versions and by the OpenTelemetry exponential histogram, at the cost of a feature flag on older setups.

Averages still have a use: `rate(_sum) / rate(_count)` gives the mean, which is handy to cross-check a percentile that looks wrong.
