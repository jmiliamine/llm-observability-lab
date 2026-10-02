"""Conversations against a real PostgreSQL: the history is shared by every API replica, survives
a restart, stays small, is purged, and is isolated from the index by its own database role.

Run with `task test:pgvector` (fake models). The index is rebuilt from the sample notes first.
"""

import os
import threading

import pytest

from lab_http import unavailable

pytestmark = pytest.mark.pgvector

WRITER = os.environ.get("PG_WRITER_DSN", "postgresql://obslab_writer:writer-local@127.0.0.1:5432/obslab")
READER = os.environ.get("PG_READER_DSN", "postgresql://obslab_reader:reader-local@127.0.0.1:5432/obslab")
CHAT = os.environ.get("PG_CHAT_DSN", "postgresql://obslab_chat:chat-local@127.0.0.1:5432/obslab")
FIRST = "How do taints and tolerations work?"
FOLLOW_UP = "And what effect does NoExecute have on them?"
NOTE = "kubernetes/taints-and-tolerations.md"


@pytest.fixture(scope="module", autouse=True)
def index():
    import psycopg

    from obslab.cli import main
    try:
        psycopg.connect(CHAT, connect_timeout=3).close()
    except psycopg.OperationalError as e:
        unavailable(f"PostgreSQL not reachable as obslab_chat ({type(e).__name__}): task test:pgvector. "
                    "A database volume created before conversations existed has no such role: "
                    "docker compose -f deploy/compose/docker-compose.yml down -v")
    with pytest.MonkeyPatch.context() as mp:
        _env(mp, WRITER)
        assert main(["ingest", "--source", "datalake"]) == 0


def _env(monkeypatch, dsn: str) -> None:
    from psycopg.conninfo import conninfo_to_dict
    info = conninfo_to_dict(dsn)
    for var, key in (("PGHOST", "host"), ("PGPORT", "port"), ("PGDATABASE", "dbname"),
                     ("PGUSER", "user"), ("PGPASSWORD", "password")):
        monkeypatch.setenv(var, str(info[key]))
    monkeypatch.setenv("OBSLAB_PROVIDER", "fake")
    monkeypatch.setenv("OBSLAB_TELEMETRY", "none")
    monkeypatch.setenv("OBSLAB_MIN_SCORE", "0.2")


@pytest.fixture
def replica(monkeypatch):
    """Builds API components the way a pod does: read-only role for the index, chat role for the
    conversations. Call it twice to get two replicas."""
    from psycopg.conninfo import conninfo_to_dict

    from obslab.app import build_components
    from obslab.config import Settings
    from obslab.telemetry import init_telemetry
    _env(monkeypatch, READER)
    monkeypatch.setenv("OBSLAB_CHAT_PASSWORD", conninfo_to_dict(CHAT)["password"])
    built = []

    def build(**settings):
        s = Settings(**settings)
        tel = init_telemetry(s)
        c = build_components(s, tel)
        built.append((c, tel))
        return c

    yield build
    for c, tel in built:
        c.close()
        tel.shutdown()


@pytest.fixture
def chat_db():
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(CHAT, autocommit=True, row_factory=dict_row) as conn:
        yield conn


def test_a_follow_up_is_served_by_another_replica(replica):
    a, b = replica(), replica()
    first = a.ask(FIRST)
    assert first["route"] == "answered" and NOTE in first["sources"]
    second = b.ask(FOLLOW_UP, first["conversation_id"])           # the other pod, same conversation
    assert second["turn"] == 2 and second["route"] == "answered" and NOTE in second["sources"]
    assert "taints" in second["standalone_question"].lower()


def test_a_conversation_survives_a_restart(replica):
    first = replica().ask(FIRST)
    again = replica()                                             # a new process would do the same
    assert again.ask(FOLLOW_UP, first["conversation_id"])["turn"] == 2


def test_one_small_checkpoint_per_turn(replica, chat_db):
    c = replica()
    cid = c.ask(FIRST)["conversation_id"]
    c.ask(FOLLOW_UP, cid)
    c.ask("How do you back up and restore etcd?", cid)
    n = chat_db.execute("SELECT count(*) AS n FROM checkpoints WHERE thread_id = %s", (cid,)).fetchone()["n"]
    assert n == 3                                                 # not one per graph node
    size = chat_db.execute(
        "SELECT coalesce(sum(octet_length(blob)), 0) AS bytes, "
        "       coalesce(bool_or(position('page_content'::bytea in blob) > 0), false) AS has_documents "
        "FROM checkpoint_blobs WHERE thread_id = %s", (cid,)).fetchone()
    assert not size["has_documents"], "retrieved chunks were saved with the conversation"
    assert size["bytes"] < 20_000, size


def test_a_failed_turn_leaves_the_conversation_as_it_was(replica):
    c = replica()
    cid = c.ask(FIRST)["conversation_id"]
    with pytest.raises(RuntimeError):
        c.ask("taints FAIL tolerations", cid)
    retry = c.ask(FOLLOW_UP, cid)
    assert retry["turn"] == 2 and retry["route"] == "answered" and NOTE in retry["sources"]


def test_a_first_question_that_fails_while_answering_does_not_count(replica):
    import uuid
    c = replica()
    cid = str(uuid.uuid4())
    with pytest.raises(RuntimeError):
        c.ask("taints FAIL tolerations", cid)        # condense passes (no history), generate fails
    first = c.ask(FIRST, cid)
    assert first["turn"] == 1 and first["standalone_question"] == FIRST


def test_the_turn_limit_holds_across_replicas(replica):
    from obslab.rag.graph import ConversationTooLongError
    a, b = replica(max_turns=2, provider="fake", telemetry="none", min_score=0.2), \
        replica(max_turns=2, provider="fake", telemetry="none", min_score=0.2)
    cid = a.ask(FIRST)["conversation_id"]
    b.ask(FOLLOW_UP, cid)
    with pytest.raises(ConversationTooLongError):
        a.ask(FIRST, cid)


def test_old_conversations_are_purged(replica, monkeypatch, capsys):
    from obslab.cli import main
    c = replica()
    cid = c.ask(FIRST)["conversation_id"]
    assert c.conversations.purge(older_than_days=1) == 0          # too recent
    assert c.ask(FOLLOW_UP, cid)["turn"] == 2

    monkeypatch.delenv("PGUSER")                                  # the purge job has the chat role only
    monkeypatch.delenv("PGPASSWORD")
    assert main(["conversations", "purge", "--days", "0"]) == 0
    assert "purged" in capsys.readouterr().out
    assert c.conversations.count() == 0
    monkeypatch.setenv("PGUSER", "obslab_reader")
    monkeypatch.setenv("PGPASSWORD", READER.split(":")[2].split("@")[0])
    assert c.ask(FOLLOW_UP, cid)["turn"] == 1                     # the history is gone


def test_two_replicas_starting_together_create_the_tables_once(replica):
    from obslab.rag import memory
    stores = [memory.ConversationStore(memory.open_pool(CHAT)) for _ in range(4)]
    errors = []

    def setup(store):
        try:
            store.ensure_tables()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=setup, args=(s,)) for s in stores]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for s in stores:
        s.close()
    assert not errors, errors


def test_not_ready_when_the_conversation_store_cannot_be_reached(replica, monkeypatch):
    assert replica().status()["ready"] is True
    monkeypatch.setenv("OBSLAB_CHAT_PASSWORD", "not-the-password")
    status = replica().status()                # e.g. a database volume that predates conversations
    assert status["ready"] is False
    assert status["error"].startswith("conversation store unreachable (")
    assert "not-the-password" not in str(status)


def test_the_two_roles_cannot_see_each_other_s_data(replica, chat_db):
    import psycopg
    replica().ask(FIRST)                                          # makes sure the chat tables exist
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        chat_db.execute("SELECT count(*) FROM rag.chunks")
    with psycopg.connect(READER, autocommit=True) as reader:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            reader.execute("SELECT count(*) FROM chat.checkpoints")
        with pytest.raises(psycopg.Error):
            reader.execute("DELETE FROM chat.checkpoints")


def test_the_conversation_pool_recovers_when_the_server_drops_connections(replica):
    import psycopg
    c = replica()
    cid = c.ask(FIRST)["conversation_id"]
    admin = os.environ.get("PG_ADMIN_DSN", "postgresql://postgres:postgres-local@127.0.0.1:5432/obslab")
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                     "WHERE usename IN ('obslab_chat', 'obslab_reader') AND pid <> pg_backend_pid()")
    assert c.ask(FOLLOW_UP, cid)["turn"] == 2
