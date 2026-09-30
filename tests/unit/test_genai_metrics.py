from obslab.telemetry.genai import DURATION_BUCKETS, TOKEN_BUCKETS, GenAIMetrics

from conftest import metrics_by_name

ATTRS = {"gen_ai.operation.name": "chat", "gen_ai.provider.name": "ollama", "gen_ai.request.model": "llama3.2:3b"}


def test_semconv_names_units_and_buckets(otel):
    tel, _, reader = otel
    m = GenAIMetrics(tel.meter, price_in=1.0, price_out=5.0)
    m.record_inference(ATTRS, duration_s=1.5, input_tokens=1000, output_tokens=200, ttfc_s=0.3)
    got = metrics_by_name(reader)
    for name in ("gen_ai.client.operation.duration", "gen_ai.client.operation.time_to_first_chunk",
                 "gen_ai.client.inference.usage.input_tokens", "gen_ai.client.inference.usage.output_tokens",
                 "gen_ai.client.inference.operation.input_tokens", "gen_ai.client.inference.operation.output_tokens",
                 "obslab.llm.cost.usd"):
        assert name in got, name
    assert list(got["gen_ai.client.operation.duration"][0].explicit_bounds) == DURATION_BUCKETS
    assert list(got["gen_ai.client.inference.operation.input_tokens"][0].explicit_bounds) == TOKEN_BUCKETS
    assert got["gen_ai.client.inference.usage.input_tokens"][0].value == 1000
    # 1000 * $1/M + 200 * $5/M
    assert abs(got["obslab.llm.cost.usd"][0].value - 0.002) < 1e-9
    assert dict(got["gen_ai.client.operation.duration"][0].attributes) == ATTRS


def test_zero_price_records_no_cost(otel):
    tel, _, reader = otel
    GenAIMetrics(tel.meter).record_inference(ATTRS, 0.1, 10, 10)
    assert "obslab.llm.cost.usd" not in metrics_by_name(reader)


def test_missing_usage_still_records_duration(otel):
    tel, _, reader = otel
    GenAIMetrics(tel.meter).record_inference(ATTRS, 0.1, None, None)
    got = metrics_by_name(reader)
    assert "gen_ai.client.operation.duration" in got
    assert "gen_ai.client.inference.usage.input_tokens" not in got
