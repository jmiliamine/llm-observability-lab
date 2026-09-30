# 0005 — Hand-written callback instrumentation

**Decision.** A ~200-line `BaseCallbackHandler` turns LangChain/LangGraph runs into OTel spans
and GenAI metrics; embeddings are wrapped explicitly (LangChain emits no callbacks for them);
retrieval gets a manual span inside the node, and each pgvector query a database client span.

**Alternatives.** OpenLLMetry (Traceloop) or OpenInference auto-instrumentation: less code and
broader coverage, but the mapping from framework events to spans is out of view.

**Consequences.** + Every attribute and parent/child link is explicit, including why `run_inline`
matters for context propagation. + Tested with in-memory exporters. − Coverage is limited to
what the handler maps; compare with an auto-instrumentor before reusing it elsewhere.
