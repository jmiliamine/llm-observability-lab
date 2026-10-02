"""Conversation memory: one LangGraph checkpoint per turn, in PostgreSQL.

A conversation is a LangGraph thread. The graph is compiled with a checkpointer, so the state of
a thread (the last turns, the turn counter) is loaded when its id comes back, on any replica.

Kept small on purpose:
  - the graph runs with durability="exit": one write per answered question, not one per node;
  - a run that fails does not change the history or the turn count, so a retry starts from the
    same conversation;
  - the state that is saved holds a few turns of text, never the retrieved chunks;
  - conversations idle for more than the retention period are deleted (`obslab conversations purge`).

Database side (deploy/shared/postgres/init-obslab.sh): the role `obslab_chat` owns the schema
`chat` and nothing else. The API keeps its read-only role for the index.
"""

from __future__ import annotations

import os
import threading

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

SCHEMA = "chat"
SETUP_LOCK = 7_421_190        # advisory lock id: two replicas starting together run the migrations once


def open_pool(dsn: str = "", *, max_size: int = 4, timeout_ms: int = 5000, connect_timeout_s: int = 3,
              name: str = "obslab-chat") -> ConnectionPool:
    """Pool for the conversation tables. `dsn` empty: host, port and database come from the PG*
    variables, the role from OBSLAB_CHAT_USER / OBSLAB_CHAT_PASSWORD."""
    kwargs: dict = {
        "autocommit": True, "prepare_threshold": 0, "row_factory": dict_row,     # what PostgresSaver expects
        "connect_timeout": connect_timeout_s, "application_name": name,
        "options": f"-c search_path={SCHEMA} -c statement_timeout={int(timeout_ms)}",
    }
    if not dsn:
        kwargs["user"] = os.environ.get("OBSLAB_CHAT_USER", "obslab_chat")
        if os.environ.get("OBSLAB_CHAT_PASSWORD"):
            kwargs["password"] = os.environ["OBSLAB_CHAT_PASSWORD"]
    return ConnectionPool(dsn, min_size=0, max_size=max_size, open=True, name=name, timeout=connect_timeout_s,
                          kwargs=kwargs, check=ConnectionPool.check_connection, max_idle=300)


class ConversationStore(PostgresSaver):
    """PostgresSaver whose tables are created on first use, not at start-up: the API must start
    (and report not ready) while the database is still coming up."""

    def __init__(self, pool: ConnectionPool):
        super().__init__(pool)
        self.pool = pool
        self._ready = False
        self._setup_lock = threading.Lock()

    def ensure_tables(self) -> None:
        if self._ready:
            return
        with self._setup_lock:
            if self._ready:
                return
            with self.pool.connection() as conn:
                conn.execute("SELECT pg_advisory_lock(%s)", (SETUP_LOCK,))
                try:
                    self.setup()            # idempotent migrations, on another pooled connection
                finally:
                    conn.execute("SELECT pg_advisory_unlock(%s)", (SETUP_LOCK,))
            self._ready = True

    def count(self) -> int:
        self.ensure_tables()
        with self.pool.connection() as conn:
            return conn.execute("SELECT count(DISTINCT thread_id) AS n FROM checkpoints").fetchone()["n"]

    def purge(self, older_than_days: float) -> int:
        """Delete the conversations whose last turn is older than the retention period."""
        self.ensure_tables()
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT thread_id FROM checkpoints GROUP BY thread_id "
                "HAVING max((checkpoint->>'ts')::timestamptz) < now() - make_interval(secs => %s)",
                (float(older_than_days) * 86400,)).fetchall()
        for row in rows:
            self.delete_thread(row["thread_id"])
        return len(rows)

    def close(self) -> None:
        self.pool.close()
