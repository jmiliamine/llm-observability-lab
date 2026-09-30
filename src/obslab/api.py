"""HTTP entry point.

- FastAPI auto-instrumentation adds the server span (http.server.request.duration)
  that parents the whole RAG trace.
- Two probe endpoints, because Kubernetes asks two different questions:
    /healthz  "is the process alive?"        -> livenessProbe (restart if not)
    /readyz   "can it serve a question now?" -> readinessProbe (remove from Service if not)
  Readiness checks what the app owns: the graph, and an index in its own database built
  with the configured embedding model. It does NOT call Ollama: if a shared dependency
  is down, every pod would turn unready at once and the Service would have zero
  endpoints -- errors are better surfaced as 502s and alerts than as a silent outage.
- On shutdown (SIGTERM from Kubernetes) the lifespan hook flushes spans, metrics and
  logs still buffered in the batch processors, so the last requests are not lost.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel, Field

from .app import Components

log = logging.getLogger("obslab.api")


class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


def create_app(components: Components) -> FastAPI:
    # Emit the *stable* HTTP semantic conventions (http.server.request.duration, seconds)
    # instead of the legacy http.server.duration in ms. Read by the instrumentation at
    # instrument time, so it must be set before instrument_app(). Env can still override.
    os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "http")
    tel = components.telemetry

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        components.close()      # database connections
        tel.shutdown()          # flush telemetry buffers before the process exits

    # FastAPI >= 0.142 has its own telemetry, which adds an OTLP exporter when
    # OTEL_EXPORTER_OTLP_ENDPOINT is set. The app already configures export, so turn that off
    # (otherwise every signal is sent twice) and hand FastAPI the app's providers.
    app = FastAPI(title="obslab RAG", lifespan=lifespan, telemetry={
        "auto_configure": False,
        "tracer_provider": tel.tracer_provider,
        "meter_provider": tel.meter_provider,
        "logger_provider": tel.logger_provider,
    })

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/readyz")
    def readyz(response: Response):
        body = components.status()
        if not body["ready"]:
            response.status_code = 503
        return body

    @app.post("/ask")
    def ask(body: Ask):
        try:
            result = components.ask(body.question)
        except Exception as e:
            # 502: a dependency (model, vector database) failed. Only the error type goes back to the
            # client; the full message, which can name hosts or users, stays on the trace.
            log.exception("ask failed")
            raise HTTPException(status_code=502, detail=f"upstream error: {type(e).__name__}") from e
        span_ctx = trace.get_current_span().get_span_context()
        result["trace_id"] = format(span_ctx.trace_id, "032x") if span_ctx.is_valid else None
        return result

    FastAPIInstrumentor.instrument_app(app, tracer_provider=tel.tracer_provider, meter_provider=tel.meter_provider,
                                       excluded_urls="healthz,readyz")   # probes would drown real traffic
    return app
