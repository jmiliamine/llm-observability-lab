"""The deployed system, end to end, as a user and an on-call would see it:

  question -> Gateway (rag.localhost) -> one of two obslab-api pods -> pgvector (PostgreSQL)
           -> model (Ollama on the host, or fakes)
           -> trace in Tempo carrying the pod identity (k8s.* resource attributes)
           -> metrics in Prometheus labelled with the namespace (collector k8sattributes)
           -> SLO recording rules evaluated by the Prometheus Operator (PrometheusRule CR)

Run with `task test:k8s` (cluster up, app deployed, index built), with either overlay.
"""

import json
import os
import subprocess
import time
import urllib.parse
from pathlib import Path

import pytest

from lab_http import is_up, request, unavailable

pytestmark = pytest.mark.k8s

RAG = os.environ.get("RAG_URL", "http://rag.localhost:8080")
PROM = os.environ.get("PROM_URL", "http://prometheus.localhost:8080")
TEMPO = os.environ.get("TEMPO_URL", "http://tempo.localhost:8080")


def _poll(fn, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        try:
            value = fn()
        except Exception:
            value = None
        if value:
            return value
        time.sleep(5)
    return None


@pytest.fixture(scope="module")
def answer():
    if not is_up(f"{RAG}/readyz"):
        unavailable(f"RAG not ready at {RAG} (task up, then kubectl -n obslab get pods)")
    return request(f"{RAG}/ask", {"question": "How do taints and tolerations work?"}, timeout=180)


def test_answer_through_the_gateway(answer):
    assert answer["route"] == "answered", answer      # the sample notes cover this question
    assert "kubernetes/taints-and-tolerations.md" in answer["sources"]
    assert answer["trace_id"] and len(answer["trace_id"]) == 32


def test_trace_carries_pod_identity(answer):
    def complete_trace():
        # wait for the full tree: Tempo serves partial traces while span batches arrive
        text = str(request(f"{TEMPO}/api/traces/{answer['trace_id']}"))
        return text if "POST /ask" in text and "invoke_workflow rag" in text else None

    text = _poll(complete_trace)
    assert text is not None, "complete trace not found in Tempo"
    assert "k8s.pod.name" in text and "obslab-api-" in text      # downward API resource attributes


def test_metrics_labelled_with_kubernetes_metadata(answer):
    # Series from the pod carry stable k8s labels (namespace, deployment) added by the collector...
    # ...but none of the duplicate uid/timestamp labels that only add cardinality.
    # We look for a CLEAN series rather than checking res[0]: right after a collector restart the
    # previous pod's series stay visible for a few minutes (staleness window). If the guard in
    # values/otel-collector.yaml were broken, no clean series would ever appear and this fails.
    churn = ("k8s_pod_uid", "k8s_pod_start_time", "k8s_replicaset_uid")
    q = urllib.parse.quote('gen_ai_invoke_workflow_duration_seconds_count{k8s_namespace_name="obslab"}')

    def clean_series():
        res = request(f"{PROM}/api/v1/query?query={q}")["data"]["result"]
        return [r["metric"] for r in res if not any(c in r["metric"] for c in churn)]

    # Metric export ~10 s + scrape 15 s, once Prometheus scrapes the collector at all: on a cluster
    # created a few minutes ago, the operator may still be loading that scrape target.
    series = _poll(clean_series, timeout=300)
    if not series:                     # say what Prometheus has instead: the labels tell which part failed
        any_ns = urllib.parse.quote("gen_ai_invoke_workflow_duration_seconds_count")
        found = [r["metric"] for r in request(f"{PROM}/api/v1/query?query={any_ns}")["data"]["result"]]
        up = request(f"{PROM}/api/v1/query?query=" + urllib.parse.quote('up{job=~".*otel.*"}'))["data"]["result"]
        pytest.fail(f"no obslab workflow series without uid/start-time labels; workflow series found: {found}; "
                    f"collector scrape targets: {[(r['metric'].get('endpoint'), r['value'][1]) for r in up]}")
    labels = series[0]
    assert labels.get("k8s_deployment_name") == "obslab-api"
    assert labels.get("k8s_pod_name", "").startswith("obslab-api-")   # per-replica identity kept


def test_slo_rules_are_evaluated(answer):
    q = urllib.parse.quote("rag:requests:rate5m")
    res = _poll(lambda: request(f"{PROM}/api/v1/query?query={q}")["data"]["result"], timeout=180)
    assert res, "recording rule rag:requests:rate5m has no data (PrometheusRule not loaded?)"


def test_ready_on_the_pgvector_index(answer):
    status = request(f"{RAG}/readyz")
    assert status["ready"] and status["store"] == "pgvector" and status["chunks"] > 0, status


def test_both_replicas_serve_from_the_shared_index(answer):
    # The index is in PostgreSQL, not in the pod: any replica can answer. Keep-alive would pin
    # one connection to one pod, and urllib opens a new connection per request.
    pods = set()
    for _ in range(12):
        r = request(f"{RAG}/ask", {"question": "What is a multi-window burn rate alert?"}, timeout=180)
        assert r["route"] == "answered"

        def pod_of(trace_id=r["trace_id"]):
            text = str(request(f"{TEMPO}/api/traces/{trace_id}"))
            i = text.find("obslab-api-")
            return text[i:i + 40].split("'")[0] if i >= 0 and "invoke_workflow rag" in text else None

        pods.add(_poll(pod_of, timeout=60))
        if len(pods - {None}) >= 2:
            break
    assert len(pods - {None}) >= 2, f"answers came from {pods}"


# ── Conversations: the history is in PostgreSQL, so either replica can continue one ──
def test_a_conversation_through_the_gateway(answer):
    first = request(f"{RAG}/ask", {"question": "How do taints and tolerations work?"}, timeout=180)
    assert first["turn"] == 1 and first["conversation_id"]
    # urllib opens a new connection per request: over a few follow-ups both replicas are hit
    for turn in range(2, 6):
        r = request(f"{RAG}/ask", {"question": "And what effect does NoExecute have on them?",
                                   "conversation_id": first["conversation_id"]}, timeout=180)
        assert r["turn"] == turn and r["conversation_id"] == first["conversation_id"], r
        assert r["route"] == "answered" and "kubernetes/taints-and-tolerations.md" in r["sources"], r
    # the follow-up was rewritten with what "them" stood for (the wording is the model's)
    assert r["standalone_question"] != "And what effect does NoExecute have on them?"


def test_conversations_are_purged_on_a_schedule(answer):
    cron = json.loads(kubectl("get", "cronjob", "obslab-purge", "-o", "json"))
    assert cron["spec"].get("suspend") is not True
    job = f"obslab-purge-test-{int(time.time())}"
    kubectl("create", "job", job, "--from=cronjob/obslab-purge")
    kubectl("wait", "--for=condition=complete", f"job/{job}", "--timeout=5m")
    assert "purged" in kubectl("logs", f"job/{job}")


# ── The data lake: notes change, the image and the API pods do not ──────────────
DATALAKE = Path(os.environ.get("OBSLAB_DATALAKE", Path(__file__).resolve().parents[2] / "datalake"))
NEW_NOTE = "runbooks/heliotrope-freeze.md"
NEW_TEXT = ("# Heliotrope deploy freeze\n\nThe Heliotrope deploy freeze starts every Thursday at 16:00 and ends "
            "on Monday at 09:00. During the Heliotrope freeze only rollbacks are deployed.\n")
NEW_QUESTION = "When does the Heliotrope deploy freeze start?"


def kubectl(*args: str, timeout: int = 1300) -> str:
    out = subprocess.run(["kubectl", "-n", "obslab", *args], capture_output=True, text=True, timeout=timeout)
    assert out.returncode == 0, out.stderr
    return out.stdout


def run_ingest() -> None:
    job = f"obslab-ingest-test-{int(time.time())}"
    kubectl("create", "job", job, "--from=cronjob/obslab-ingest")
    kubectl("wait", "--for=condition=complete", f"job/{job}", "--timeout=20m")


def api_pods() -> dict:
    """{pod name: image} of the running API replicas."""
    pods = json.loads(kubectl("get", "pods", "-l", "app.kubernetes.io/name=obslab-api", "-o", "json"))["items"]
    return {p["metadata"]["name"]: p["spec"]["containers"][0]["image"] for p in pods}


def test_only_the_ingest_job_mounts_the_data_lake(answer):
    api = json.loads(kubectl("get", "deploy", "obslab-api", "-o", "json"))["spec"]["template"]["spec"]
    assert not [v for v in api.get("volumes", []) if "persistentVolumeClaim" in v], "the API must not see the notes"
    cron = json.loads(kubectl("get", "cronjob", "obslab-ingest", "-o", "json"))
    spec = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    mount = next(m for m in spec["containers"][0]["volumeMounts"] if m["mountPath"] == "/datalake")
    assert mount["readOnly"] is True


def test_a_new_note_is_served_without_a_new_image(answer):
    note = DATALAKE / NEW_NOTE
    if not DATALAKE.is_dir():
        unavailable(f"data lake folder not found on the host: {DATALAKE} (set OBSLAB_DATALAKE)")
    # Sources, not the route: with real embeddings an unknown subject can still retrieve a
    # loosely related note, and the model then says it does not know.
    assert NEW_NOTE not in request(f"{RAG}/ask", {"question": NEW_QUESTION}, timeout=180)["sources"]
    pods = api_pods()
    note.parent.mkdir(exist_ok=True)
    note.write_text(NEW_TEXT, encoding="utf-8")
    try:
        run_ingest()
        r = request(f"{RAG}/ask", {"question": NEW_QUESTION}, timeout=180)
        assert r["route"] == "answered" and NEW_NOTE in r["sources"], r
        assert "thursday" in r["answer"].lower(), r["answer"]       # the answer comes from the new note
        assert api_pods() == pods, "same pods, same image: only the index changed"
    finally:
        note.unlink()
        note.parent.rmdir()
        run_ingest()
    assert NEW_NOTE not in request(f"{RAG}/ask", {"question": NEW_QUESTION}, timeout=180)["sources"]
