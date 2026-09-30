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
