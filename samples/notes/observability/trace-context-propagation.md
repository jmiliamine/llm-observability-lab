# Trace context propagation

A distributed trace is a tree of spans that share one trace ID. Propagation is how that ID crosses process boundaries.

Over HTTP, OpenTelemetry uses the W3C `traceparent` header by default:

    traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01

The fields are the version, the 16-byte trace ID, the 8-byte ID of the parent span and flags (01 means sampled). `tracestate` carries vendor-specific data alongside it.

Instrumentation libraries do the work. The client side injects the header into outgoing requests, the server side extracts it and starts its span as a child. When a hop has no instrumentation, the chain breaks and you get two unrelated traces.

Inside one process, context flows through the current span. In Python that is a context variable, so it follows `asyncio` tasks correctly, but it does not follow work handed to a thread pool unless you pass the context explicitly.

Logs join the trace when the logging handler reads the current span and writes its trace ID and span ID on each record. Loki can then link a log line to the trace in Tempo, and Tempo can link back to the logs of a span.

Baggage is a separate header for key-value pairs that should travel with the request (a tenant ID, for example). It is not added to spans automatically, and it is sent to every downstream service, so never put secrets in it.

Sampling decisions travel with the context too: with parent-based sampling, a service keeps a span if its parent was sampled.
