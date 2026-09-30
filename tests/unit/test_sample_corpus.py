"""The demo corpus and the load generator must agree: every in-domain question of `obslab load`
is answered from samples/notes in fake mode, and off-topic questions fall back. If a note is
removed or a question changed, this fails before the cluster demo shows only fallbacks."""

from pathlib import Path

import pytest
from langchain_core.vectorstores import InMemoryVectorStore

from obslab.app import build_components
from obslab.cli import QUESTIONS_IN, QUESTIONS_OFF
from obslab.rag import corpus
from obslab.rag.providers import HashingEmbeddings

NOTES = Path(__file__).resolve().parents[2] / "samples" / "notes"


@pytest.fixture(scope="module")
def sample_store():
    docs = corpus.split(corpus.load_folder(NOTES))
    assert len(docs) > 20
    s = InMemoryVectorStore(HashingEmbeddings())
    s.add_documents(docs)
    return s


@pytest.mark.parametrize("question", QUESTIONS_IN)
def test_load_questions_are_answered_from_the_samples(question, settings, otel, sample_store):
    c = build_components(settings, otel[0], store=sample_store)
    r = c.ask(question)
    assert r["route"] == "answered", question
    assert r["sources"]


@pytest.mark.parametrize("question", QUESTIONS_OFF)
def test_off_topic_questions_fall_back(question, settings, otel, sample_store):
    c = build_components(settings, otel[0], store=sample_store)
    assert c.ask(question)["route"] == "fallback"
