# 0001 — OpenTelemetry + GenAI semantic conventions

**Context.** LLM calls need the same signals as any dependency (latency, errors) plus
new ones (tokens, time-to-first-chunk, cost). Many tools offer an SDK for this
(LangSmith, Langfuse, Phoenix, vendor APMs), each with its own data model.

**Decision.** Instrument with the OpenTelemetry SDK only, and name everything after the
GenAI semantic conventions (`gen_ai.client.operation.duration`,
`gen_ai.client.inference.usage.*`, `gen_ai.operation.name`, `gen_ai.provider.name`…),
checked against the `open-telemetry/semantic-conventions-genai` repository.

**Alternatives.** LangSmith (best LangChain UX, SaaS, proprietary) · Langfuse / Arize Phoenix
(open source, LLM-first, a second observability silo next to the SRE stack) · custom names.

**Consequences.** + One standard for app, infra and LLM signals; any backend works; the
names are what observability platforms (Datadog, Grafana, cloud APMs) recognise.
− The GenAI conventions are still *development*: names can change (they already moved
token metrics to `gen_ai.client.inference.*`). Mitigation: names live in one module
(`telemetry/genai.py`) and the conventions version is noted in the README.
