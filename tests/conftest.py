"""Shared fixtures: fake providers + in-memory OTel exporters (no network, no Docker)."""

from __future__ import annotations

import pytest
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from obslab.app import build_components
from obslab.config import Settings
from obslab.rag.providers import HashingEmbeddings
from obslab.telemetry import init_telemetry

CORPUS = [
    ("vectors.md", "Cosine similarity measures the angle between two embedding vectors. "
                   "Vector search ranks documents by cosine similarity to the query embedding."),
    ("k8s-probes.md", "A liveness probe restarts a container that is stuck. "
                      "A readiness probe removes a pod from service endpoints until it can serve traffic."),
    ("etcd.md", "Back up etcd with etcdctl snapshot save and restore it with etcdctl snapshot restore "
                "into a new data directory."),
]


@pytest.fixture
def settings():
    return Settings(provider="fake", telemetry="none", top_k=3, min_score=0.2, price_in=1.0, price_out=5.0)


@pytest.fixture
def otel(settings):
    spans, reader = InMemorySpanExporter(), InMemoryMetricReader()
    tel = init_telemetry(settings, span_exporter=spans, metric_reader=reader)
    yield tel, spans, reader
    tel.shutdown()


@pytest.fixture
def store():
    s = InMemoryVectorStore(HashingEmbeddings())
    s.add_documents([Document(page_content=t, metadata={"source": n}) for n, t in CORPUS])
    return s


@pytest.fixture
def components(settings, otel, store):
    tel, _, _ = otel
    return build_components(settings, tel, store=store)


def metrics_by_name(reader: InMemoryMetricReader):
    """{metric name: [data points]} from an in-memory reader."""
    out = {}
    data = reader.get_metrics_data()
    for rm in (data.resource_metrics if data else []):
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                out.setdefault(m.name, []).extend(m.data.data_points)
    return out


def spans_by_name(exporter: InMemorySpanExporter):
    return {s.name: s for s in exporter.get_finished_spans()}
