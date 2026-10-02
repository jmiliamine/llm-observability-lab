"""Conversations: a follow-up question is understood from the previous turns, at a bounded cost.

Fake models and in-memory checkpoints (same LangGraph mechanics as PostgreSQL; the real database
is covered by tests/e2e/test_conversations.py).
"""

import dataclasses
import uuid

import pytest

from obslab.app import build_components
from obslab.config import Settings
from obslab.rag.graph import ConversationTooLongError

from conftest import metrics_by_name

FIRST = "How do you back up etcd?"
FOLLOW_UP = "How often should that be done?"        # means nothing without the first question
OFF_TOPIC = "What is the best recipe for a chocolate cake?"


def thread(conversation_id: str) -> dict:
    return {"configurable": {"thread_id": conversation_id}}


def chat_spans(spans) -> list:
    return [s for s in spans.get_finished_spans() if s.name.startswith("chat ")]


def test_the_first_question_starts_a_conversation_without_an_extra_model_call(components, otel):
    _, spans, _ = otel
    r = components.ask(FIRST)
    assert r["route"] == "answered" and r["sources"] == ["etcd.md"]
    assert r["turn"] == 1 and r["standalone_question"] == FIRST
    assert uuid.UUID(r["conversation_id"])
    assert len(chat_spans(spans)) == 1                  # generate only: nothing to condense yet


def test_a_follow_up_is_answered_thanks_to_the_previous_turn(components, otel):
    _, spans, _ = otel
    assert components.ask(FOLLOW_UP)["route"] == "fallback"     # alone, it matches no note

    first = components.ask(FIRST)
    spans.clear()
    second = components.ask(FOLLOW_UP, first["conversation_id"])
    assert second["conversation_id"] == first["conversation_id"] and second["turn"] == 2
    assert second["route"] == "answered" and second["sources"] == ["etcd.md"]
    assert "etcd" in second["standalone_question"]
    assert len(chat_spans(spans)) == 2                  # condense + generate
    nodes = [s.name for s in spans.get_finished_spans() if s.name.startswith("rag.node ")]
    assert nodes[0] == "rag.node condense"


def test_conversations_do_not_see_each_other(components):
    first = components.ask(FIRST)
    other = components.ask("What does a readiness probe do?")
    assert other["conversation_id"] != first["conversation_id"]
    in_other = components.ask(FOLLOW_UP, other["conversation_id"])
    assert "etcd" not in in_other["standalone_question"] and "etcd.md" not in in_other["sources"]


def test_an_unrelated_follow_up_is_not_dragged_back_to_the_previous_subject(components):
    first = components.ask(FIRST)
    r = components.ask(OFF_TOPIC, first["conversation_id"])
    assert r["route"] == "fallback" and r["standalone_question"] == OFF_TOPIC


def test_the_saved_state_is_a_few_turns_of_text(settings, otel, store):
    c = build_components(dataclasses.replace(settings, history_turns=2), otel[0], store=store)
    cid = c.ask(FIRST)["conversation_id"]
    for question in ("What does a readiness probe do?", "What is cosine similarity?", FOLLOW_UP):
        c.ask(question, cid)
    saved = c.graph.get_state(thread(cid)).values
    assert saved["turn"] == 4
    assert [m.type for m in saved["messages"]] == ["human", "ai", "human", "ai"]      # the last 2 turns
    assert saved["messages"][-2].content == FOLLOW_UP
    assert saved["hits"] == [] and saved["relevant"] == []       # no retrieved chunk in a checkpoint
    assert len(list(c.graph.get_state_history(thread(cid)))) == 4    # one checkpoint per turn, not per node


def test_history_can_be_turned_off(settings, otel, store):
    c = build_components(dataclasses.replace(settings, history_turns=0), otel[0], store=store)
    first = c.ask(FIRST)
    second = c.ask(FOLLOW_UP, first["conversation_id"])
    assert second["route"] == "fallback" and second["standalone_question"] == FOLLOW_UP
    assert c.graph.get_state(thread(first["conversation_id"])).values["messages"] == []


def test_a_conversation_has_a_maximum_length(settings, otel, store):
    c = build_components(dataclasses.replace(settings, max_turns=2), otel[0], store=store)
    cid = c.ask(FIRST)["conversation_id"]
    c.ask(FOLLOW_UP, cid)
    with pytest.raises(ConversationTooLongError):
        c.ask("What does a readiness probe do?", cid)
    assert c.graph.get_state(thread(cid)).values["turn"] == 2       # the refused question left no trace
    assert c.ask("What does a readiness probe do?")["turn"] == 1    # a new conversation works


def test_a_failed_turn_leaves_the_conversation_as_it_was(components):
    cid = components.ask(FIRST)["conversation_id"]
    with pytest.raises(RuntimeError):
        components.ask("cosine similarity FAIL vectors", cid)
    saved = components.graph.get_state(thread(cid)).values
    assert saved["turn"] == 1 and len(saved["messages"]) == 2
    retry = components.ask(FOLLOW_UP, cid)                          # the retry is turn 2, not 3
    assert retry["turn"] == 2 and retry["route"] == "answered"


def test_a_first_question_that_fails_while_answering_does_not_count(components):
    cid = str(uuid.uuid4())
    with pytest.raises(RuntimeError):
        components.ask("cosine similarity FAIL vectors", cid)       # condense passes, generate fails
    first = components.ask(FIRST, cid)
    assert first["turn"] == 1 and first["standalone_question"] == FIRST


def test_a_turn_starts_clean_even_after_a_rewrite(components):
    cid = components.ask(OFF_TOPIC)["conversation_id"]              # goes through rewrite, then fallback
    r = components.ask("What does a readiness probe do?", cid)
    assert r["route"] == "answered" and r["rewrites"] == 0 and r["sources"] == ["k8s-probes.md"]


def test_the_conversation_id_is_on_the_span_and_never_on_a_metric(components, otel):
    _, spans, reader = otel
    first = components.ask(FIRST)
    components.ask(FOLLOW_UP, first["conversation_id"])
    workflows = [s for s in spans.get_finished_spans() if s.name == "invoke_workflow rag"]
    assert {s.attributes["gen_ai.conversation.id"] for s in workflows} == {first["conversation_id"]}

    metrics = metrics_by_name(reader)
    turns = metrics["rag.conversation.turn"][0]
    assert turns.count == 2 and turns.sum == 3                      # turn 1 + turn 2
    for points in metrics.values():
        for point in points:
            assert first["conversation_id"] not in {str(v) for v in point.attributes.values()}


@pytest.mark.parametrize("kwargs,message", [
    ({"history_turns": -1}, "OBSLAB_HISTORY_TURNS"),
    ({"history_turns": 11}, "OBSLAB_HISTORY_TURNS"),
    ({"max_turns": 0}, "OBSLAB_MAX_TURNS"),
    ({"conversation_ttl_days": 0}, "OBSLAB_CONVERSATION_TTL_DAYS"),
])
def test_invalid_conversation_settings_fail_at_startup(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Settings(**kwargs)


@pytest.mark.parametrize("follow_up,rewrite,expected", [
    # the rewrite only added what "it" stood for: accepted
    ("Why does it use two windows?", "Why does a multi-window burn rate alert use two windows?",
     "Why does a multi-window burn rate alert use two windows?"),
    ("Is there a threshold?", '"Is there a threshold for cosine similarity?"\nExplanation: ...',
     "Is there a threshold for cosine similarity?"),
    # the model drifted back to the previous subject: the question is used as typed
    ("What is the best recipe for a chocolate cake?", "How does a taint on a node repel pods?",
     "What is the best recipe for a chocolate cake?"),
    ("How do you back up etcd?", "", "How do you back up etcd?"),
    # nothing but references in the follow-up: whatever the model resolved is taken
    ("And about that?", "What about the NoExecute taint effect?", "What about the NoExecute taint effect?"),
])
def test_a_rewrite_that_lost_the_question_is_discarded(follow_up, rewrite, expected):
    from obslab.rag.graph import standalone_question
    assert standalone_question(follow_up, rewrite) == expected
