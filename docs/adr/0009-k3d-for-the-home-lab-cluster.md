# 0009 — k3d (k3s in Docker) for the home-lab cluster

**Context.** Kubernetes on an ordinary laptop: Windows, Docker Desktop with about 2 cores /
10 GB for its VM, a GPU used by Ollama.

**Options weighed.**

| Option | Footprint | Realism | Verdict |
|---|---|---|---|
| VirtualBox + 2–3 Ubuntu VMs (kubeadm or k3s) | 3 × 2–4 GB, a full OS each; VirtualBox conflicts with Hyper-V/WSL2 on Windows | Highest (real nodes, real OS) | Too heavy for a laptop; a good fit for a spare mini-PC |
| minikube (docker driver) | ~2 GB, kubeadm control plane | Good, many addons | Single node by default, heavier than k3s |
| kind | ~0.5–1 GB per node | Upstream Kubernetes; the CI favourite | No ingress/storage/LB batteries; great for CI |
| Docker Desktop Kubernetes | built in | Low control (version, nodes, registry) | Hides the parts this lab is about |
| **k3d (k3s)** | **~450–500 MiB per node** | **k3s = the home-lab/edge standard, CNCF certified** | **Chosen** |

**Decision.** k3d with 1 server + 1 agent, pinned k3s (v1.36.4), a k3d-managed OCI registry,
node memory caps (3 GB / 5 GB), Traefik (bundled) as the Gateway API implementation.

**Consequences.** + Same distribution as a home lab on Raspberry Pis or a mini-PC: the
manifests move as is. + `task stop` frees the RAM in seconds, `task start` brings everything back.
− k3s specifics to know: scheduler/controller-manager/etcd embedded (their scrapes disabled),
Traefik configured through `HelmChartConfig`, bundled Gateway API CRDs (ADR 0011).
− Two "nodes" share one VM: node failures are simulated (`kubectl drain`), not real.

**Version policy.** Follow the k3s *stable* channel, never a `.0`; one minor at a time;
kubectl within +/-1 minor of the server, checked by `task doctor` (`scripts/doctor.py`), which
also reports a `kubectl.exe` in `C:\Windows` (Windows resolves it before the PATH for spawned
processes). Upgrade = recreate the cluster from `k3d.yaml` (immutable nodes, ~25 min with the
platform).
