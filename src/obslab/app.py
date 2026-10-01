"""Composition root: builds telemetry, models, vector store and the RAG graph once."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.vectorstores import InMemoryVectorStore, VectorStore

from .config import Settings
from .rag.graph import RagApp
from .rag.pgvector import PgVectorStore, open_pool
from .rag.providers import chat_model, embeddings
from .telemetry import GenAIMetrics, RagMetrics, Telemetry
from .telemetry.callbacks import OTelCallbackHandler

EMPTY_INDEX = "index is empty: run the ingest (task app:ingest, or obslab ingest)"


@dataclass
class Components:
    settings: Settings
    telemetry: Telemetry
    genai: GenAIMetrics
    rag: RagApp
    graph: object

    def ask(self, question: str):
        return self.rag.ask(question, self.graph)

    def status(self) -> dict:
        """What /readyz reports. The vector store is checked on every call: the index can be
        rebuilt, or the database restarted, while the API keeps running."""
        store = self.rag.store
        kind = "pgvector" if isinstance(store, PgVectorStore) else "memory"
        if isinstance(store, PgVectorStore):
            try:
                meta, chunks = store.status()
            except Exception as e:      # the message may carry connection details: keep the type only
                return {"ready": False, "store": kind, "chunks": 0,
                        "error": f"vector database unreachable ({type(e).__name__})"}
            error = check_index_meta(self.settings, meta) if meta else EMPTY_INDEX
        else:                       # the in-memory double the tests pass in
            chunks = len(store.store)
            error = None if chunks else EMPTY_INDEX
        body = {"ready": self.graph is not None and chunks > 0 and error is None,
                "store": kind, "provider": self.settings.provider, "chunks": chunks}
        if error:
            body["error"] = error
        return body

    def close(self) -> None:
        pool = getattr(self.rag.store, "pool", None)
        if pool is not None:
            pool.close()


def open_store(settings: Settings, telemetry: Telemetry, emb) -> PgVectorStore:
    """The index in PostgreSQL. Connection settings come from the libpq PG* variables."""
    pool = open_pool(timeout_ms=settings.db_timeout_ms, name=settings.service_name)
    return PgVectorStore(pool, emb, tracer=telemetry.tracer)


def build_components(settings: Settings, telemetry: Telemetry,
                     store: VectorStore | None = None) -> Components:
    genai = GenAIMetrics(telemetry.meter, settings.price_in, settings.price_out)
    rag_metrics = RagMetrics(telemetry.meter)
    emb = embeddings(settings, telemetry, genai)
    if store is None:
        store = open_store(settings, telemetry, emb)
    elif isinstance(store, InMemoryVectorStore):
        store.embedding = emb
    handler = OTelCallbackHandler(telemetry, genai, rag_metrics)
    rag = RagApp(settings, telemetry, store, chat_model(settings), handler, rag_metrics)
    return Components(settings, telemetry, genai, rag, rag.build())


def check_index_meta(settings: Settings, meta: dict) -> str | None:
    """None if the index can be queried with the configured embedding model, else why not."""
    built_with = meta.get("embed_model")
    if built_with != settings.embed_model_id:
        return (f"index built with embed model {built_with!r}, but {settings.embed_model_id!r} is configured: "
                "run the ingest again")
    return None
