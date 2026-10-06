# Security

This lab is meant to run on a local machine. The UIs are served over plain HTTP on
`*.localhost`, and the API has no authentication. Every port the cluster and the Compose stack
publish is bound to 127.0.0.1, so nothing is reachable from the network. Do not change that
binding to expose the lab as is.

What it does take care of:

- Pods run under the restricted Pod Security Standard: non-root, read-only root filesystem,
  no privilege escalation, no service account token mounted.
- The Grafana admin password and the database passwords are generated at install time,
  stored in Secrets, and never printed by the tasks that create them.
- The API reaches PostgreSQL with a read-only role; only the ingest job can write the index,
  and only those two workloads may connect to the database (NetworkPolicy). Errors returned to
  clients carry an error type, not connection details.
- The Compose stack uses fixed local-only database passwords on a port bound to 127.0.0.1;
  set `OBSLAB_*_PASSWORD` in a `.env` file to change them.
- Prompts and answers are not recorded in telemetry unless `OBSLAB_CAPTURE_CONTENT=true`.
- Your notes stay on your machine: they are read from a local folder, indexed into a local
  database, and the models run locally.

## What is checked automatically

`task scan` runs the same checks as CI, each failing on a finding:

| Check | Tool | Scope |
|---|---|---|
| Workflow lint and audit | actionlint, zizmor | `.github/workflows/` (pinned actions, permissions, credential handling) |
| Secrets | gitleaks | every commit |
| Dependencies | Trivy | `uv.lock`, HIGH and CRITICAL |
| Misconfigurations | Trivy | Dockerfile, Compose file, rendered Kubernetes manifests; accepted findings and their reasons are in `.trivyignore.yaml` |
| Image | Trivy | the built image, fixable HIGH and CRITICAL |

The image is built from `uv.lock`, gets Debian's security updates at build time and ships
without pip. GitHub Actions are pinned to commit SHAs and the scanners to image digests;
Dependabot proposes the updates. CI also runs weekly, so a new CVE shows up without a push.

## Reporting a vulnerability

Please do not open a public issue. Use **Report a vulnerability** in the Security tab of the
repository (GitHub private vulnerability reporting), with the details and the steps to
reproduce. I will answer within a week.
