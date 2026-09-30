# Liveness, readiness and startup probes

Kubernetes asks a container three different questions, and each probe answers one of them.

A **liveness probe** asks "is this process stuck?". When it fails `failureThreshold` times in a row, the kubelet kills the container and restarts it. Use it for deadlocks and hung event loops, nothing else. A liveness probe that calls a database turns a database outage into a restart storm.

A **readiness probe** asks "can this pod take traffic right now?". When it fails, the pod is removed from the endpoints of every Service that selects it. Nothing is restarted. Readiness is the right place to check what the pod owns: configuration loaded, caches warm, an index in memory. It should not check shared dependencies, because then every replica goes unready at the same moment and the Service ends up with zero endpoints.

A **startup probe** protects slow starters. While it has not succeeded, liveness and readiness are not run. A pod that needs two minutes to load a model gets `periodSeconds: 5` and `failureThreshold: 24` on its startup probe, and a tight liveness probe once it is up.

Typical settings for an HTTP API:

- liveness: `GET /healthz`, period 20s, timeout 3s, failure threshold 3
- readiness: `GET /readyz`, period 10s, timeout 3s
- startup: `GET /healthz`, period 5s, failure threshold sized on the worst measured start

Probes run from the kubelet on the node, so a NetworkPolicy that only allows traffic from the gateway does not block them.
