#!/bin/sh
# First-start initialisation of the database (run once by the postgres image entrypoint,
# from /docker-entrypoint-initdb.d, when the data directory is empty). Shared by compose and k8s.
#
# Least privilege:
#   obslab_writer  owns schema `rag`; used only by the ingest job to rebuild the index
#   obslab_reader  SELECT on `rag` only; used by the API, which can therefore never alter the index
#   obslab_chat    owns schema `chat` (the conversations) and sees nothing of `rag`; used by the API
#                  for the conversation history, and by the purge job
# Nobody but the superuser can create objects in `public`.
set -eu

: "${OBSLAB_WRITER_PASSWORD:?missing}"
: "${OBSLAB_READER_PASSWORD:?missing}"
: "${OBSLAB_CHAT_PASSWORD:?missing}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v writer_pw="$OBSLAB_WRITER_PASSWORD" -v reader_pw="$OBSLAB_READER_PASSWORD" \
     -v chat_pw="$OBSLAB_CHAT_PASSWORD" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;

CREATE ROLE obslab_writer LOGIN PASSWORD :'writer_pw' CONNECTION LIMIT 4;
CREATE ROLE obslab_reader LOGIN PASSWORD :'reader_pw' CONNECTION LIMIT 20;
CREATE ROLE obslab_chat   LOGIN PASSWORD :'chat_pw'   CONNECTION LIMIT 20;

REVOKE ALL ON DATABASE :"DBNAME" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"DBNAME" TO obslab_writer, obslab_reader, obslab_chat;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

CREATE SCHEMA rag AUTHORIZATION obslab_writer;
GRANT USAGE ON SCHEMA rag TO obslab_reader;
-- Tables the writer creates later (each rebuild creates a new one) are readable by the reader.
ALTER DEFAULT PRIVILEGES FOR ROLE obslab_writer IN SCHEMA rag GRANT SELECT ON TABLES TO obslab_reader;
-- Defence in depth: the reader cannot run away with a slow query even if the client forgets.
ALTER ROLE obslab_reader SET statement_timeout = '5s';
ALTER ROLE obslab_reader SET default_transaction_read_only = on;

-- Conversations (LangGraph checkpoints). The app creates and migrates its tables in this schema.
CREATE SCHEMA chat AUTHORIZATION obslab_chat;
ALTER ROLE obslab_chat SET search_path = chat;
ALTER ROLE obslab_chat SET statement_timeout = '5s';
SQL
