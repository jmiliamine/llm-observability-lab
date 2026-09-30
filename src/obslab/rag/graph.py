"""The RAG workflow as an explicit LangGraph state machine.

            ┌──────────┐  relevant docs  ┌──────────┐    ┌───────┐
  START ──▶ │ retrieve │ ──────────────▶ │ generate │ ─▶ │ grade │ ─▶ END
            └──────────┘                 └──────────┘    └───────┘
               │   ▲ none relevant, 1st time
               ▼   │
            ┌─────────┐            none relevant again ┌──────────┐
            │ rewrite │  (LLM reformulates the query)  │ fallback │ ─▶ END
            └─────────┘ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ▶└──────────┘

Why a graph and not a single chain: every branch (rewrite, fallback) is a
named node, so it becomes a span and a metric label — the "why was this answer
bad" question gets an observable answer.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_core.documents import Document
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.vectorstores import VectorStore
from langgraph.graph import END, START, StateGraph
from opentelemetry import context as otel_context
from opentelemetry.trace import SpanKind

from ..config import Settings
from ..telemetry.callbacks import OTelCallbackHandler
from ..telemetry.genai import OP, RagMetrics
from ..telemetry.setup import Telemetry

log = logging.getLogger("obslab.rag")
MAX_REWRITES = 1
STOP = set("the a an of to in and or is are was what how why which with for on "
           "de la le les des un une et est que qui pour dans".split())
FALLBACK_ANSWER = "I don't know: nothing relevant in my notes for this question."

SYSTEM = ("You answer questions using ONLY the provided context from the user's notes. "
          "If the context is insufficient, say you don't know. Answer in 3-6 sentences.")


class RagState(TypedDict, total=False):
    question: str
    query: str
    hits: list[tuple[Document, float]]
    relevant: list[tuple[Document, float]]
    rewrites: int
    answer: str
    route: str               # answered | fallback
    groundedness: float


def groundedness(answer: str, context: str) -> float:
    """Cheap, deterministic proxy: share of answer content words present in the context."""
    words = [w for w in re.findall(r"[a-zà-ÿ0-9]{3,}", answer.lower()) if w not in STOP]
    if not words:
        return 0.0
    ctx = set(re.findall(r"[a-zà-ÿ0-9]{3,}", context.lower()))
    return round(sum(w in ctx for w in words) / len(words), 3)


@dataclass
class RagApp:
    settings: Settings
    telemetry: Telemetry
    store: VectorStore
    llm: BaseChatModel
    handler: OTelCallbackHandler
    rag_metrics: RagMetrics
    index_name: str = "notes"

    # ── helpers ──────────────────────────────────────────────────────────────
    def _node_ctx(self, config: RunnableConfig):
        cb = (config or {}).get("callbacks")
        return self.handler.context_for(getattr(cb, "parent_run_id", None))

    # ── nodes ────────────────────────────────────────────────────────────────
    def retrieve(self, state: RagState, config: RunnableConfig) -> dict[str, Any]:
        query = state.get("query") or state["question"]
        token = otel_context.attach(self._node_ctx(config))
        try:
            with self.telemetry.tracer.start_as_current_span(
                    f"retrieval {self.index_name}", kind=SpanKind.INTERNAL,
                    attributes={OP: "retrieval", "gen_ai.data_source.id": self.index_name,
                                "gen_ai.retrieval.top_k": self.settings.top_k}) as span:
                hits = self.store.similarity_search_with_score(query, k=self.settings.top_k)
                relevant = [(d, s) for d, s in hits if s >= self.settings.min_score]
                top = max((s for _, s in hits), default=0.0)
                span.set_attribute("rag.retrieval.documents", len(hits))
                span.set_attribute("rag.retrieval.relevant_documents", len(relevant))
                span.set_attribute("rag.retrieval.top_score", round(float(top), 4))
                if self.telemetry.capture_content:
                    span.set_attribute("gen_ai.retrieval.query.text", query)
        finally:
            otel_context.detach(token)
        attrs = {"gen_ai.data_source.id": self.index_name}
        self.rag_metrics.documents.record(len(hits), attrs)
        self.rag_metrics.relevant.record(len(relevant), attrs)
        if hits:
            self.rag_metrics.top_score.record(float(top), attrs)
        return {"query": query, "hits": hits, "relevant": relevant}

    def route_after_retrieve(self, state: RagState) -> str:
        if state.get("relevant"):
            return "generate"
        return "rewrite" if state.get("rewrites", 0) < MAX_REWRITES else "fallback"

    def rewrite(self, state: RagState, config: RunnableConfig) -> dict[str, Any]:
        msg = self.llm.invoke([HumanMessage(
            content="Rewrite this question as a short search query with key technical terms.\n"
                    f"Question: {state['question']}")], config)
        self.rag_metrics.rewrites.add(1, {"gen_ai.data_source.id": self.index_name})
        return {"query": str(msg.content).strip()[:300], "rewrites": state.get("rewrites", 0) + 1}

    def generate(self, state: RagState, config: RunnableConfig) -> dict[str, Any]:
        context = "\n\n---\n\n".join(d.page_content for d, _ in state["relevant"])
        messages = [SystemMessage(content=SYSTEM),
                    HumanMessage(content=f"Context:\n{context}\n\nQuestion: {state['question']}")]
        # Streaming on purpose: it is what makes time-to-first-chunk measurable.
        answer = "".join(str(c.content) for c in self.llm.stream(messages, config))
        return {"answer": answer.strip(), "route": "answered"}

    def fallback(self, state: RagState) -> dict[str, Any]:
        self.rag_metrics.fallbacks.add(1, {"reason": "no_relevant_context"})
        return {"answer": FALLBACK_ANSWER, "route": "fallback", "groundedness": 0.0}

    def grade(self, state: RagState) -> dict[str, Any]:
        context = " ".join(d.page_content for d, _ in state.get("relevant", []))
        score = groundedness(state.get("answer", ""), context)
        self.rag_metrics.groundedness.record(score, {"gen_ai.data_source.id": self.index_name})
        return {"groundedness": score}

    # ── graph ────────────────────────────────────────────────────────────────
    def build(self):
        g = StateGraph(RagState)
        g.add_node("retrieve", self.retrieve)
        g.add_node("rewrite", self.rewrite)
        g.add_node("generate", self.generate)
        g.add_node("fallback", self.fallback)
        g.add_node("grade", self.grade)
        g.add_edge(START, "retrieve")
        g.add_conditional_edges("retrieve", self.route_after_retrieve,
                                {"generate": "generate", "rewrite": "rewrite", "fallback": "fallback"})
        g.add_edge("rewrite", "retrieve")
        g.add_edge("generate", "grade")
        g.add_edge("grade", END)
        g.add_edge("fallback", END)
        return g.compile(name="rag")

    def ask(self, question: str, graph=None) -> dict[str, Any]:
        graph = graph or self.build()
        state = graph.invoke({"question": question, "rewrites": 0}, config={"callbacks": [self.handler]})
        sources = sorted({d.metadata.get("source", "?") for d, _ in state.get("relevant", [])})
        log.info("rag answered", extra={"rag.route": state.get("route"), "rag.rewrites": state.get("rewrites", 0),
                                        "rag.groundedness": state.get("groundedness", 0.0)})
        return {"answer": state.get("answer", ""), "route": state.get("route"), "sources": sources,
                "rewrites": state.get("rewrites", 0), "groundedness": state.get("groundedness", 0.0)}
