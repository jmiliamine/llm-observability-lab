# Pod security baseline

Pod Security Admission applies one of three profiles per namespace through labels: `privileged`, `baseline` and `restricted`. The `restricted` profile is a good default for application namespaces:

    metadata:
      labels:
        pod-security.kubernetes.io/enforce: restricted

To pass `restricted`, a pod needs:

- `runAsNonRoot: true`, with a numeric UID in the image or the pod spec.
- `allowPrivilegeEscalation: false` on every container.
- All capabilities dropped: `capabilities: {drop: [ALL]}`.
- `seccompProfile: {type: RuntimeDefault}`.
- No hostPath volumes, host network or host PID.

Two more settings are not required by the profile but worth having:

- `readOnlyRootFilesystem: true`, with an `emptyDir` mounted where the app really writes (usually `/tmp`).
- `automountServiceAccountToken: false` when the pod never calls the Kubernetes API. A stolen token is worth nothing if it was never mounted.

A numeric UID matters: Kubernetes can only verify `runAsNonRoot` if it knows the UID. An image that says `USER app` without a number fails admission.

`fsGroup` makes mounted volumes writable by the app group, which is often needed for PersistentVolumes created by a local-path provisioner.

Use `kubectl label --dry-run=server --overwrite ns <name> pod-security.kubernetes.io/enforce=restricted` to see which running pods would be rejected before you enforce it.
