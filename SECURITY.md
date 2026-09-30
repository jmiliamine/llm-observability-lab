# Security

This lab is meant to run on a local machine. The UIs are served over plain HTTP on
`*.localhost`, and the Compose stack gives anonymous read-only access to Grafana. Do not expose
it on a network as is.

What it does take care of:

- Pods run under the restricted Pod Security Standard: non-root, read-only root filesystem,
  no privilege escalation, no service account token mounted (`docs/adr/0012`).
- The Grafana admin password and the database passwords are generated at install time,
  stored in Secrets, and never printed by the tasks that create them.
- The API reaches PostgreSQL with a read-only role; only the ingest job can write the index,
  and only those two workloads may connect to the database (NetworkPolicy). Errors returned to
  clients carry an error type, not connection details (`docs/adr/0008`).
- The Compose stack uses fixed local-only database passwords on a port bound to 127.0.0.1;
  set `OBSLAB_*_PASSWORD` in a `.env` file to change them.
- Prompts and answers are not recorded in telemetry unless `OBSLAB_CAPTURE_CONTENT=true`.
- Your notes stay on your machine: they are copied into a local image and a local database,
  and the models run locally.

## Reporting a vulnerability

Please do not open a public issue. Send an e-mail to jmili.amine@gmail.com with the details
and the steps to reproduce. I will answer within a week.
