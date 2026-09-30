# 0004 — LangGraph state machine for the RAG flow

**Context.** A basic RAG is one chain: retrieve → prompt → LLM. Real failures hide in the
branches: nothing relevant retrieved, query needs rewriting, answer not grounded.

**Decision.** Model the flow as a LangGraph `StateGraph`: `retrieve → (generate | rewrite ↺ |
fallback) → grade`, with at most one rewrite.

**Alternatives.** Single LCEL chain (simpler, but branches become `if`s inside one span) ·
LangChain agents (non-deterministic tool loops, harder to reason about for a first lab).

**Consequences.** + Every branch is a named node → its own span, its own duration metric and a
label; "why was this answer bad" becomes a query. + Room for tools and agents in the same graph.
− More code than a chain; LangGraph emits many internal runs, filtered in the callback handler.
