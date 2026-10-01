"""obslab <command>

  ingest [--source DIR]          chunk + embed a folder of .md/.txt notes into the index
  ask "question" [--url ...]     one question, prints answer + trace id (in-process, or a running API)
  serve [--port 8000]            HTTP API (POST /ask)
  load [--n 30] [--url ...] [--host-header H]   traffic generator (in-domain + off-topic questions)
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.request
from pathlib import Path

QUESTIONS_IN = [
    "What is cosine similarity used for in vector search?",
    "How does a Kubernetes liveness probe differ from a readiness probe?",
    "How do you back up and restore etcd?",
    "How do taints and tolerations work?",
    "What does chunk overlap change in a RAG pipeline?",
    "What is a multi-window burn rate alert?",
    "Why should metric labels have low cardinality?",
    "What does the OpenTelemetry Collector do?",
]
QUESTIONS_OFF = [
    "What is the best recipe for a chocolate cake?",
    "Who won the 1998 football world cup?",
]


def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")


def _components(settings=None, telemetry=None):
    from .app import build_components
    from .config import Settings
    from .telemetry import init_telemetry
    settings = settings or Settings()
    telemetry = telemetry or init_telemetry(settings, set_global=True)
    return build_components(settings, telemetry)


def cmd_ingest(a) -> int:
    from .config import Settings
    from .rag import corpus, pgvector
    from .rag.providers import embeddings
    from .telemetry import GenAIMetrics, init_telemetry
    settings = Settings()
    tel = init_telemetry(settings, set_global=True)
    docs = corpus.split(corpus.load_folder(Path(a.source)))
    if not docs:
        print(f"no .md/.txt files under {a.source}", file=sys.stderr)
        return 1
    meta = {"provider": settings.provider, "embed_model": settings.embed_model_id}
    emb = embeddings(settings, tel, GenAIMetrics(tel.meter))
    start = time.perf_counter()
    with tel.tracer.start_as_current_span("ingest", attributes={"obslab.chunks": len(docs)}):
        with pgvector.open_pool(name="obslab-ingest") as pool:
            pgvector.rebuild(pool, docs, emb, meta)
    tel.shutdown()
    print(f"indexed {len(docs)} chunks in {time.perf_counter() - start:.1f}s -> PostgreSQL (rag.chunks)")
    return 0


def _post_ask(url: str, question: str, host_header: str = "", timeout: float = 180) -> dict:
    headers = {"Content-Type": "application/json"}
    if host_header:
        # Behind the cluster Gateway, routing is by Host header (rag.localhost); Windows does
        # not resolve *.localhost, so we hit 127.0.0.1 and send the Host header ourselves.
        headers["Host"] = host_header
    req = urllib.request.Request(f"{url}/ask", data=json.dumps({"question": question}).encode(),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def cmd_ask(a) -> int:
    if a.url:                       # ask the deployed API instead of running the graph here
        print(json.dumps(_post_ask(a.url, a.question, a.host_header), indent=2, ensure_ascii=False))
        return 0
    c = _components()
    with c.telemetry.tracer.start_as_current_span("cli.ask") as span:
        result = c.ask(a.question)
        result["trace_id"] = format(span.get_span_context().trace_id, "032x")
    c.telemetry.shutdown()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_serve(a) -> int:
    import uvicorn

    from .api import create_app
    uvicorn.run(create_app(_components()), host=a.host, port=a.port)
    return 0


def cmd_load(a) -> int:
    ok = err = 0
    for i in range(a.n):
        q = random.choice(QUESTIONS_OFF if random.random() < a.off_topic else QUESTIONS_IN)
        t = time.perf_counter()
        try:
            body = _post_ask(a.url, q, a.host_header)
            ok += 1
            print(f"{i + 1:>3} {time.perf_counter() - t:5.1f}s {body.get('route'):<9} {q[:60]}")
        except Exception as e:
            err += 1
            print(f"{i + 1:>3} ERROR {e}")
        time.sleep(a.pause)
    print(f"done: {ok} ok, {err} errors")
    return 0 if err == 0 else 1


def main(argv=None) -> int:
    _utf8()
    ap = argparse.ArgumentParser(prog="obslab")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest")
    s.add_argument("--source", default="samples/notes", help="folder of .md/.txt notes")
    s.set_defaults(fn=cmd_ingest)

    s = sub.add_parser("ask")
    s.add_argument("question")
    s.add_argument("--url", default="", help="ask a running API (e.g. http://127.0.0.1:8080) instead of in-process")
    s.add_argument("--host-header", default="", help="e.g. rag.localhost:8080 when --url is the Gateway IP")
    s.set_defaults(fn=cmd_ask)

    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("load")
    s.add_argument("--n", type=int, default=30)
    s.add_argument("--url", default="http://127.0.0.1:8000")
    s.add_argument("--off-topic", type=float, default=0.2)
    s.add_argument("--pause", type=float, default=0.5)
    s.add_argument("--host-header", default="", help="e.g. rag.localhost:8080 when --url is the Gateway IP")
    s.set_defaults(fn=cmd_load)

    a = ap.parse_args(argv)
    return a.fn(a)

if __name__ == "__main__":
    sys.exit(main())
