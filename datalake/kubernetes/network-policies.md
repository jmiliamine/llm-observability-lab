# NetworkPolicies

By default every pod can talk to every other pod in the cluster. A NetworkPolicy restricts that for the pods it selects. Policies are allow-lists: once a pod is selected by any policy for a direction (ingress or egress), only what is explicitly allowed gets through.

A common starting point is to deny everything in a namespace and then open what is needed:

    apiVersion: networking.k8s.io/v1
    kind: NetworkPolicy
    metadata: {name: default-deny}
    spec:
      podSelector: {}
      policyTypes: [Ingress, Egress]

Then allow the API to receive traffic from the ingress controller namespace only:

    ingress:
      - from:
          - namespaceSelector:
              matchLabels: {kubernetes.io/metadata.name: kube-system}
        ports: [{port: 8000}]

Egress rules are easy to forget. A pod with default-deny egress cannot resolve names until you allow UDP and TCP port 53 to the cluster DNS. It also cannot export telemetry until you allow the collector port (4318 for OTLP/HTTP).

NetworkPolicies are enforced by the CNI plugin, not by Kubernetes itself. Calico, Cilium and the embedded policy controller of k3s enforce them; plain flannel does not. A policy applied on a cluster whose CNI ignores it is silently useless, so test it: run a throwaway pod and try to reach something that should be blocked.

Kubelet probes are not affected, because they come from the node itself.
