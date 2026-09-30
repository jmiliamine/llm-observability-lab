# OpenTelemetry GenAI semantic conventions

The GenAI semantic conventions define standard names for telemetry about model calls, so dashboards and tools work across providers and frameworks.

Spans are named `{operation} {model}`, for example `chat llama3.2:3b` or `embeddings nomic-embed-text`, with attributes such as:

- `gen_ai.operation.name`: `chat`, `embeddings`, `invoke_agent`, `execute_tool`...
- `gen_ai.provider.name`: who serves the model.
- `gen_ai.request.model` and `gen_ai.response.model`.
- `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens`.
- `error.type` when the call fails.

Two metrics cover most dashboards:

- `gen_ai.client.operation.duration` (histogram, seconds).
- `gen_ai.client.token.usage` (histogram, tokens), split by `gen_ai.token.type` = `input` or `output`.

Metric attributes stay low cardinality: operation, provider, model, error type. Prompt and completion content is never a metric attribute. The conventions allow content on spans or events, but it is opt-in, because prompts often carry personal data. A sensible default is off, with a flag to turn it on in development.

The conventions are still marked as in development, and some names changed between versions. Keeping every name in one module of the application makes a rename a one-file change.

Frameworks such as LangChain do not always emit these names. A callback handler that maps framework events to GenAI spans and metrics gives you standard telemetry without waiting for upstream support.
