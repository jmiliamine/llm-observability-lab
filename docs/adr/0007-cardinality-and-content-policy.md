# 0007 — Bounded labels, content capture opt-in

**Decision.** Metric attributes are bounded enums only: operation, provider, model, node,
reason, error.type. Question text, prompts, answers, user or session ids never become labels.
Prompt/answer text goes on spans only when `OBSLAB_CAPTURE_CONTENT=true` (the conventions mark
`gen_ai.input.messages` / `gen_ai.output.messages` as Opt-In).

**Why.** Each distinct label value is a new Prometheus series (memory, cost); prompts can hold
personal or confidential data. Traces are sampled and short-lived, metrics are not.

**In Kubernetes.** The collector's `k8sattributes` processor with
`resource_to_telemetry_conversion` would turn every resource attribute into a label, including
`k8s_pod_uid`, `k8s_pod_start_time`, `k8s_replicaset_uid` and `k8s_cluster_uid`, which change on
every rollout. A `resource/metric-labels` processor in the metrics pipeline deletes those
(traces and logs keep them). `k8s_pod_name` stays: without it two replicas would write the same
series and overwrite each other's counters. `task test:k8s` asserts both rules.

**Consequences.** + Series count stays predictable (a few hundred for the app). + Safe default
for any shared backend. − Debugging a bad answer needs content capture switched on, or the logs.
