# Requests and limits

**Requests** are what the scheduler reserves. A pod requesting 500m CPU and 512Mi memory is only placed on a node with that much unreserved capacity. Requests are also what the kubelet uses to share CPU under contention.

**Limits** are enforced at runtime by the kernel. Memory and CPU behave very differently:

- Going over the memory limit gets the container OOM-killed (exit code 137, reason `OOMKilled`).
- Going over the CPU limit only throttles the container. It keeps running, slower, and latency percentiles get worse in ways that are hard to spot.

That is why many teams set a memory limit on every container but no CPU limit, and size CPU requests from measurements instead. The CPU request still guarantees a fair share under contention.

The QoS class follows from these values:

- `Guaranteed`: requests equal limits for every resource of every container.
- `Burstable`: at least one request is set.
- `BestEffort`: nothing is set. First to be evicted under node pressure.

Sizing from data: run the workload under realistic load, read `container_memory_working_set_bytes` and `container_cpu_usage_seconds_total` in Prometheus, set the memory request near the steady state and the limit with headroom for peaks (1.5x to 2x). An idle measurement is not a sizing: a Grafana pod that sits at 150 MiB can pass 400 MiB when dashboards load.

A LimitRange gives defaults to pods that set nothing, and a ResourceQuota caps the total for a namespace.
