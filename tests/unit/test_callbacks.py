import json

import pytest
from langchain_core.messages import HumanMessage
from opentelemetry.trace import SpanKind, StatusCode

from obslab.config import Settings
from obslab.rag.providers import FakeChat
from obslab.telemetry import GenAIMetrics, RagMetrics, init_telemetry
from obslab.telemetry.callbacks import OTelCallbackHandler

from conftest import metrics_by_name, spans_by_name


def _handler(tel):
    return OTelCallbackHandler(tel, GenAIMetrics(tel.meter), RagMetrics(tel.meter))


def test_chat_span_and_token_metrics(otel):
    tel, spans, reader = otel
    FakeChat().invoke([HumanMessage(content="Context: Alpha beta. Question: what?")],
                      config={"callbacks": [_handler(tel)]})
    span = spans_by_name(spans)["chat fake-chat"]
    assert span.kind == SpanKind.CLIENT
    a = span.attributes
    assert a["gen_ai.operation.name"] == "chat"
    assert a["gen_ai.provider.name"] == "obslab.fake"
    assert a["gen_ai.request.model"] == "fake-chat"
    assert a["gen_ai.usage.input_tokens"] > 0 and a["gen_ai.usage.output_tokens"] > 0
    assert "gen_ai.input.messages" not in a            # content capture is opt-in
    got = metrics_by_name(reader)
    assert got["gen_ai.client.operation.duration"][0].count == 1
    assert got["gen_ai.client.inference.usage.output_tokens"][0].value == a["gen_ai.usage.output_tokens"]


def test_streaming_records_time_to_first_chunk(otel):
    tel, spans, reader = otel
    list(FakeChat().stream([HumanMessage(content="Context: One two three. Question: q")],
                           config={"callbacks": [_handler(tel)]}))
    assert "obslab.time_to_first_chunk_s" in spans_by_name(spans)["chat fake-chat"].attributes
    assert "gen_ai.client.operation.time_to_first_chunk" in metrics_by_name(reader)


def test_error_sets_status_and_error_type(otel):
    tel, spans, reader = otel
    with pytest.raises(RuntimeError):
        FakeChat().invoke([HumanMessage(content="FAIL please")], config={"callbacks": [_handler(tel)]})
    span = spans_by_name(spans)["chat fake-chat"]
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["error.type"] == "RuntimeError"
    point = metrics_by_name(reader)["gen_ai.client.operation.duration"][0]
    assert point.attributes["error.type"] == "RuntimeError"


def test_content_capture_opt_in(settings):
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    spans = InMemorySpanExporter()
    tel = init_telemetry(Settings(provider="fake", capture_content=True), span_exporter=spans,
                         metric_reader=InMemoryMetricReader())
    FakeChat().invoke([HumanMessage(content="Context: Secret. Question: x")], config={"callbacks": [_handler(tel)]})
    a = spans_by_name(spans)["chat fake-chat"].attributes
    assert json.loads(a["gen_ai.input.messages"])[0]["content"].startswith("Context:")
    assert "gen_ai.output.messages" in a
    tel.shutdown()


def test_a_node_retried_by_a_retry_policy_shows_every_attempt(otel):
    """A RetryPolicy runs the node again inside the same step. LangGraph's task stream reports the
    start and the final result only; the callbacks fire for every attempt, so each one is a span."""
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph
    from langgraph.types import RetryPolicy

    class State(TypedDict, total=False):
        n: int

    calls = []

    def flaky(state):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("first attempt fails")
        return {"n": len(calls)}

    tel, spans, reader = otel
    handler = _handler(tel)
    g = StateGraph(State)
    g.add_node("flaky", flaky, retry_policy=RetryPolicy(max_attempts=3, initial_interval=0.01, jitter=False,
                                                         retry_on=ConnectionError))
    g.add_edge(START, "flaky")
    g.add_edge("flaky", END)
    assert g.compile(name="probe").invoke({"n": 0}, config={"callbacks": [handler]}) == {"n": 2}

    attempts = sorted((s for s in spans.get_finished_spans() if s.name == "rag.node flaky"),
                      key=lambda s: s.attributes["langgraph.attempt"])
    assert [s.attributes["langgraph.attempt"] for s in attempts] == [1, 2]
    assert len({s.attributes["langgraph.step"] for s in attempts}) == 1          # same step, not a loop
    failed, passed = attempts
    assert failed.status.status_code == StatusCode.ERROR
    assert failed.attributes["error.type"] == "ConnectionError"
    assert passed.status.status_code != StatusCode.ERROR
    assert spans_by_name(spans)["invoke_workflow rag"].status.status_code != StatusCode.ERROR

    retries = metrics_by_name(reader)["rag.graph.node.retries"]
    assert [(dict(p.attributes), p.value) for p in retries] == [({"langgraph.node": "flaky"}, 1)]
    assert handler._attempts == {}                                                # nothing kept after the run


def test_a_loop_in_the_graph_is_not_counted_as_a_retry(components, otel):
    """The rewrite loop runs `retrieve` twice in two different steps: two first attempts."""
    _, spans, reader = otel
    assert components.ask("Best chocolate cake recipe for a birthday party?")["rewrites"] == 1
    retrieves = [s for s in spans.get_finished_spans() if s.name == "rag.node retrieve"]
    assert len(retrieves) == 2
    assert [s.attributes["langgraph.attempt"] for s in retrieves] == [1, 1]
    assert len({s.attributes["langgraph.step"] for s in retrieves}) == 2
    assert "rag.graph.node.retries" not in metrics_by_name(reader)
