# Rolling updates without downtime

A Deployment replaces pods gradually. Two fields drive it:

- `maxSurge`: how many extra pods may exist during the rollout.
- `maxUnavailable`: how many pods may be missing compared to `replicas`.

With `maxSurge: 1` and `maxUnavailable: 0`, Kubernetes starts one new pod, waits until it is Ready, then stops one old pod, and repeats. Capacity never drops. This only works if the readiness probe is honest: a pod that reports Ready before it can serve will receive traffic and fail it.

The other half of a clean rollout is shutdown. When a pod is deleted:

1. It is removed from the Service endpoints, asynchronously.
2. At the same time the container receives SIGTERM.
3. After `terminationGracePeriodSeconds` (30 by default) it gets SIGKILL.

Because steps 1 and 2 race, a server that exits immediately on SIGTERM can drop requests still being routed to it. A short `preStop` sleep or a graceful shutdown in the app closes that gap. The shutdown hook is also where buffered telemetry must be flushed, or the last spans of a pod never reach the backend.

Follow a rollout with `kubectl rollout status deploy/<name>` and undo it with `kubectl rollout undo`. Keep `revisionHistoryLimit` small, since every old ReplicaSet stays as an object.

Image tags must be immutable. With `:latest`, two pods of the same ReplicaSet can run different code.
