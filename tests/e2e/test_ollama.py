"""The RAG with the real local models: nomic-embed-text for retrieval, llama3.2:3b for answers.

Checks what the fakes cannot: the calibrated threshold (OBSLAB_MIN_SCORE=0.6) still separates
in-domain from off-topic questions on samples/notes, and the model answers from the context.
Run with `task test:ollama` (Ollama running, both models pulled). Telemetry is not exported.
"""

import dataclasses
from pathlib import Path

import pytest

from lab_http import is_up, unavailable

pytestmark = pytest.mark.ollama

NOTES = Path(__file__).resolve().parents[2] / "samples" / "notes"


@pytest.fixture(scope="module")
def rag():
    from langchain_core.vectorstores import InMemoryVectorStore

    from obslab.app import build_components
    from obslab.config import Settings
    from obslab.rag import corpus
    from obslab.rag.providers import embeddings
    from obslab.telemetry import GenAIMetrics, init_telemetry

    settings = dataclasses.replace(Settings(), provider="ollama", telemetry="none")
    if not is_up(f"{settings.ollama_url}/api/version"):
        unavailable(f"Ollama not reachable at {settings.ollama_url}")
    tel = init_telemetry(settings)
    docs = corpus.split(corpus.load_folder(NOTES))
    store = InMemoryVectorStore(embeddings(settings, tel, GenAIMetrics(tel.meter)))
    store.add_documents(docs)
    yield build_components(settings, tel, store=store)
    tel.shutdown()


def test_in_domain_question_is_answered_from_the_right_note(rag):
    r = rag.ask("How do taints and tolerations work?")
    assert r["route"] == "answered", r
    assert "kubernetes/taints-and-tolerations.md" in r["sources"]
    assert "toleration" in r["answer"].lower()


def test_off_topic_question_falls_back(rag):
    assert rag.ask("What is the best recipe for a chocolate cake?")["route"] == "fallback"
