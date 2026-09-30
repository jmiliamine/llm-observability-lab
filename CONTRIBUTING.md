# Contributing

Thanks for taking a look. This is a personal lab, but issues and pull requests are welcome,
especially reports from Linux or macOS, where it has not been tested yet.

## Getting set up

```bash
task setup
```

```bash
task test
```

`task test` runs offline in a few seconds. You do not need the cluster to work on the app
or the telemetry code.

## Before opening a pull request

- `task lint` and `task test` pass.
- If you touched manifests or the platform, say which of `task test:stack`, `task test:k8s`
  and `task test:ollama` you ran, and on which OS.
- A new component or a design trade-off comes with a short ADR in `docs/adr/`
  (context, decision, alternatives, consequences).
- Dashboards and alert rules are generated: edit `scripts/gen_observability.py` or
  `deploy/shared/`, then `task gen`.

## Style

- Python 3.14, formatted and linted with Ruff (line length 120).
- Comments explain why, not what. Kubernetes manifests follow the same rule.
- Metric names and attributes follow the OpenTelemetry GenAI conventions and live in
  `src/obslab/telemetry/genai.py`.

## Reporting a bug

Include the output of `task doctor`, your OS, and the command that failed with its full output.
