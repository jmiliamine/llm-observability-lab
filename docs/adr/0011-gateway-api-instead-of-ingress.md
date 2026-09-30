# 0011 — Gateway API instead of Ingress

**Context.** ingress-nginx reached end of life on 2026-03-24 (no more CVE fixes). The Gateway API
is the Kubernetes successor, implemented by Traefik, Envoy Gateway, Cilium and the cloud providers.

**Decision.** One shared `Gateway` (namespace `gateway`, owned by the platform) listening on
`*.localhost`; apps attach `HTTPRoute`s from namespaces labelled `obslab.dev/gateway-access=true`.
Traefik (bundled with k3s) is the implementation; its Ingress provider is disabled. The Gateway
API CRDs come from k3s's own `traefik-crd` chart, which owns them: they are not installed
separately, and upgrading them means upgrading k3s.

**Consequences.** + Role split (the platform owns listeners, apps own routes), per-route timeouts,
portable to other implementations. − Windows does not resolve `*.localhost` outside
browsers: tests send the Host header to 127.0.0.1, and OTLP from the host uses a NodePort (:4318).
