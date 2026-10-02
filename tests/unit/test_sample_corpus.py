"""The demo corpus and the load generator must agree: every in-domain question of `obslab load`
is answered from the sample notes (datalake/) in fake mode, and off-topic questions fall back. If a note is
removed or a question changed, this fails before the cluster demo shows only fallbacks."""

from pathlib import Path

import pytest
from langchain_core.vectorstores import InMemoryVectorStore

from obslab.app import build_components
from obslab.cli import FOLLOW_UPS, QUESTIONS_IN, QUESTIONS_OFF
from obslab.rag import corpus
from obslab.rag.providers import HashingEmbeddings

NOTES = Path(__file__).resolve().parents[2] / "datalake"


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


@pytest.mark.parametrize("question,follow_up", list(FOLLOW_UPS.items()))
def test_load_follow_ups_are_answered_from_the_same_note(question, follow_up, settings, otel, sample_store):
    assert question in QUESTIONS_IN
    c = build_components(settings, otel[0], store=sample_store)
    first = c.ask(question)
    second = c.ask(follow_up, first["conversation_id"])
    assert second["route"] == "answered", second
    assert set(first["sources"]) & set(second["sources"]), (first["sources"], second["sources"])
