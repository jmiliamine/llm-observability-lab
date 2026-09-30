# Taints and tolerations

A taint is set on a node and repels pods. A toleration is set on a pod and lets it ignore a matching taint. Together they keep workloads off nodes where they do not belong.

    kubectl taint nodes gpu-1 nvidia.com/gpu=present:NoSchedule

The effect decides what happens to pods without a matching toleration:

- `NoSchedule`: new pods are not placed on the node; running pods stay.
- `PreferNoSchedule`: the scheduler avoids the node when it can.
- `NoExecute`: new pods are not placed and running pods are evicted, optionally after `tolerationSeconds`.

A toleration in the pod spec:

    tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule

A toleration only *allows* a pod on a tainted node; it does not attract it there. To pin a workload to GPU nodes you combine the toleration with a node selector or node affinity. The usual pattern for dedicated nodes is taint + toleration + affinity.

Kubernetes also taints nodes by itself: `node.kubernetes.io/not-ready` and `node.kubernetes.io/unreachable` with `NoExecute`. Every pod gets a default toleration of 300 seconds for these, which is why pods on a dead node are only rescheduled after about five minutes.

Control-plane nodes carry `node-role.kubernetes.io/control-plane:NoSchedule`, so ordinary workloads stay on workers.
