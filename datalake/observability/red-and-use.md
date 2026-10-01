# RED and USE

Two checklists decide what to put on a first dashboard.

**RED** is for request-driven services:

- **Rate**: requests per second.
- **Errors**: failed requests per second, or the error ratio.
- **Duration**: latency distribution, shown as percentiles.

**USE** is for resources such as CPU, memory, disks and queues:

- **Utilization**: how busy the resource is.
- **Saturation**: how much work is waiting (run queue, swap, queue depth).
- **Errors**: device or resource errors.

A service dashboard starts with RED at the top, because that is what users feel. USE panels for the pods and nodes underneath explain why RED moved.

For an LLM application, RED needs a few additions: tokens per request (input and output), time to first token when streaming, the share of requests that fell back to "I don't know", and an estimated cost. Those come from the OpenTelemetry GenAI metrics rather than from HTTP metrics.

A good first question during an incident is "is it rate, errors or duration?", followed by "which resource is saturated?". Having both checklists on one screen answers them in a minute.
