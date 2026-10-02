"""The data lake drives the index: what `obslab ingest` finds in the folder is what the API answers
from, and nothing else changes.

Run with `task test:pgvector` (same PostgreSQL as test_pgvector.py, fake models). Each test works
on a copy of the sample notes in a temporary folder and runs the real CLI, with the writer role
for the ingest and the read-only role for the questions, like the two workloads in the cluster.
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from lab_http import unavailable

pytestmark = pytest.mark.pgvector

WRITER = os.environ.get("PG_WRITER_DSN", "postgresql://obslab_writer:writer-local@127.0.0.1:5432/obslab")
READER = os.environ.get("PG_READER_DSN", "postgresql://obslab_reader:reader-local@127.0.0.1:5432/obslab")
CHAT_PASSWORD = os.environ.get("OBSLAB_CHAT_PASSWORD", "chat-local")
SAMPLES = Path(__file__).resolve().parents[2] / "datalake"
NEW_NOTE = "runbooks/heliotrope-freeze.md"
NEW_TEXT = ("# Heliotrope deploy freeze\n\nThe Heliotrope deploy freeze starts every Thursday at 16:00 and ends "
            "on Monday at 09:00. During the Heliotrope freeze only rollbacks are deployed.\n")
QUESTION = "When does the Heliotrope deploy freeze start?"


def _as(monkeypatch, dsn: str) -> None:
    """Point the libpq variables at one role, as the Deployment and the CronJob do."""
    from psycopg.conninfo import conninfo_to_dict
    info = conninfo_to_dict(dsn)
    for var, key in (("PGHOST", "host"), ("PGPORT", "port"), ("PGDATABASE", "dbname"),
                     ("PGUSER", "user"), ("PGPASSWORD", "password")):
        monkeypatch.setenv(var, str(info[key]))


@pytest.fixture
def lake(tmp_path, monkeypatch):
    import psycopg
    try:
        psycopg.connect(WRITER, connect_timeout=3).close()
    except psycopg.OperationalError as e:
        unavailable(f"PostgreSQL not reachable ({type(e).__name__}): task stack:up, or task test:pgvector")
    monkeypatch.setenv("OBSLAB_PROVIDER", "fake")
    monkeypatch.setenv("OBSLAB_TELEMETRY", "none")
    monkeypatch.setenv("OBSLAB_MIN_SCORE", "0.2")
    folder = tmp_path / "datalake"
    shutil.copytree(SAMPLES, folder)
    return folder


def ingest(monkeypatch, folder: Path) -> int:
    from obslab.cli import main
    _as(monkeypatch, WRITER)
    return main(["ingest", "--source", str(folder)])


def ask(monkeypatch, question: str) -> tuple[dict, dict]:
    """(answer, readiness) from an API built the way the Deployment builds it: read-only role."""
    from obslab.app import build_components
    from obslab.config import Settings
    from obslab.telemetry import init_telemetry
    _as(monkeypatch, READER)
    monkeypatch.setenv("OBSLAB_CHAT_PASSWORD", CHAT_PASSWORD)       # the API also keeps conversations
    settings = Settings()
    tel = init_telemetry(settings)
    c = build_components(settings, tel)
    try:
        return c.ask(question), c.status()
    finally:
        c.close()
        tel.shutdown()


def test_a_note_added_to_the_data_lake_is_answered_after_ingest(lake, monkeypatch):
    assert ingest(monkeypatch, lake) == 0
    before, status = ask(monkeypatch, QUESTION)
    assert before["route"] == "fallback", before            # nothing in the samples about it
    chunks = status["chunks"]

    (lake / NEW_NOTE).parent.mkdir()
    (lake / NEW_NOTE).write_text(NEW_TEXT, encoding="utf-8")
    assert ingest(monkeypatch, lake) == 0
    after, status = ask(monkeypatch, QUESTION)
    assert after["route"] == "answered", after
    assert NEW_NOTE in after["sources"]
    assert status["chunks"] == chunks + 1


def test_a_note_removed_from_the_data_lake_is_forgotten_after_ingest(lake, monkeypatch):
    (lake / NEW_NOTE).parent.mkdir()
    (lake / NEW_NOTE).write_text(NEW_TEXT, encoding="utf-8")
    assert ingest(monkeypatch, lake) == 0
    assert ask(monkeypatch, QUESTION)[0]["route"] == "answered"

    (lake / NEW_NOTE).unlink()
    assert ingest(monkeypatch, lake) == 0
    answer, _ = ask(monkeypatch, QUESTION)
    assert answer["route"] == "fallback" and NEW_NOTE not in answer["sources"], answer
    # the other notes are still there
    assert "kubernetes/etcd-backup.md" in ask(monkeypatch, "How do you back up and restore etcd?")[0]["sources"]


def test_only_text_notes_are_read(lake, monkeypatch):
    (lake / "heliotrope.pdf").write_bytes(NEW_TEXT.encode())
    (lake / "heliotrope.json").write_text(json.dumps({"note": QUESTION}), encoding="utf-8")
    assert ingest(monkeypatch, lake) == 0
    answer, _ = ask(monkeypatch, QUESTION)
    assert answer["route"] == "fallback", answer


@pytest.mark.parametrize("state", ["empty", "missing"])
def test_an_empty_or_missing_data_lake_leaves_the_index_alone(lake, monkeypatch, tmp_path, capsys, state):
    assert ingest(monkeypatch, lake) == 0
    _, good = ask(monkeypatch, "How do taints and tolerations work?")
    assert good["ready"] and good["chunks"] > 0

    bad = tmp_path / state
    if state == "empty":
        bad.mkdir()
        (bad / "picture.png").write_bytes(b"not a note")
    assert ingest(monkeypatch, bad) == 1
    assert ("no .md/.txt notes" if state == "empty" else "data lake not found") in capsys.readouterr().err

    answer, status = ask(monkeypatch, "How do taints and tolerations work?")
    assert status == good                                    # same index, still serving
    assert answer["route"] == "answered"
