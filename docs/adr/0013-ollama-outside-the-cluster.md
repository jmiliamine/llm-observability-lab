# 0013 — Ollama stays outside the cluster

**Context.** The laptop GPU is used by Ollama on the host. Exposing it inside k3d means the NVIDIA
container toolkit in WSL2, GPU-enabled k3s images and the device plugin: fragile on a laptop.

**Decision.** Ollama runs on the host; the cluster reaches it through an `ExternalName` Service
(`ollama` → `host.docker.internal`). An ExternalName is only a DNS alias, so the HTTP Host header
keeps the name the client used, and Ollama only accepts Host names it trusts (DNS-rebinding
protection), `*.local` among them. The app therefore calls
`http://ollama.obslab.svc.cluster.local:11434`.

**Consequences.** + Full GPU speed, no driver plumbing. + A common pattern: an external
dependency behind a cluster-native name (a managed database, a hosted model API...). − Not managed
by Kubernetes (no probes, no metrics from Ollama itself): its health shows only through the app's
`gen_ai.client.operation.duration{error_type}` and the error alerts.
