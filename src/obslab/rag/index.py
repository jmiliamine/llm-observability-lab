"""In-memory vector index (LangChain's InMemoryVectorStore) persisted to a JSON file.

For offline development and tests (OBSLAB_VECTOR_STORE=memory). Deployments use
PostgreSQL + pgvector (rag/pgvector.py, ADR 0008); both give the same scores.

A small sidecar file (`<index>.meta.json`) records which embedding model built the
index. Vectors from two different models are not comparable, so the API refuses to
serve (readiness 503) when the index and the configured model do not match.
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore


def meta_path(path: Path) -> Path:
    return path.with_name(path.stem + ".meta.json")


def build(docs: list[Document], embeddings: Embeddings, path: Path, batch: int = 64,
          meta: dict | None = None) -> InMemoryVectorStore:
    store = InMemoryVectorStore(embeddings)
    for i in range(0, len(docs), batch):
        store.add_documents(docs[i:i + batch])
    path.parent.mkdir(parents=True, exist_ok=True)
    store.dump(str(path))
    if meta is not None:
        meta_path(path).write_text(json.dumps({**meta, "chunks": len(docs)}, indent=2), encoding="utf-8")
    return store


def load(path: Path, embeddings: Embeddings) -> InMemoryVectorStore:
    if not path.exists():
        raise FileNotFoundError(f"no index at {path}. Build it first: obslab ingest --source <folder>")
    return InMemoryVectorStore.load(str(path), embeddings)


def load_meta(path: Path) -> dict | None:
    p = meta_path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
