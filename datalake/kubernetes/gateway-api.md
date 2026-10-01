# Gateway API

Gateway API is the successor to Ingress. It splits one object into several, owned by different people:

- **GatewayClass**: which controller implements the gateways (Traefik, Envoy Gateway, Istio, cloud load balancers). Owned by the infrastructure provider.
- **Gateway**: a listener, meaning a port, a protocol and optionally a hostname and TLS certificate. Owned by the platform team.
- **HTTPRoute**: routing rules for one application, attached to a Gateway. Owned by the app team, in the app namespace.

A Gateway decides which namespaces may attach routes with `allowedRoutes`, so an app team cannot hijack a hostname it does not own.

An HTTPRoute that sends `rag.example.test` to a Service:

    apiVersion: gateway.networking.k8s.io/v1
    kind: HTTPRoute
    metadata: {name: rag, namespace: rag}
    spec:
      parentRefs: [{name: shared, namespace: gateway}]
      hostnames: [rag.example.test]
      rules:
        - backendRefs: [{name: rag-api, port: 8000}]

What Ingress could only do with controller-specific annotations is part of the spec: header matching, traffic splitting by weight (canary releases), request mirroring, redirects and rewrites.

Check the status of a route with `kubectl describe httproute`: the `Accepted` and `ResolvedRefs` conditions tell you whether the Gateway took it and whether the backend Service exists. Most "404 from the gateway" problems show up there.
