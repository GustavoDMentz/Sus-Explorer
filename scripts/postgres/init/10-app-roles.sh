#!/usr/bin/env bash
# Creates the four least-privilege LOGIN roles on first start of the Postgres container
# (docker-entrypoint-initdb.d). The superuser from POSTGRES_USER is for this bootstrap only.
#
# Passwords come from the environment (compose passes them from .env, which is not versioned);
# this file contains none. psql quotes them as literals (:'var'), so any characters are safe.
set -euo pipefail

for name in POSTGRES_MIGRATOR_PASSWORD POSTGRES_INGEST_PASSWORD POSTGRES_HISTORY_PASSWORD POSTGRES_READER_PASSWORD; do
  if [ -z "${!name:-}" ]; then
    echo "ERRO: $name não definida; veja .env.example" >&2
    exit 1
  fi
done

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v migrator_password="$POSTGRES_MIGRATOR_PASSWORD" \
  -v ingest_password="$POSTGRES_INGEST_PASSWORD" \
  -v history_password="$POSTGRES_HISTORY_PASSWORD" \
  -v reader_password="$POSTGRES_READER_PASSWORD" <<'SQL'
-- Structural groups (migrations also create them when missing).
SELECT format('CREATE ROLE %I NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', r)
FROM unnest(ARRAY['sus_explorer_migrator','sus_explorer_runtime','sus_explorer_reader','sus_explorer_history']) AS r
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)
\gexec

-- Logins: one group each, never more, and none of them is a superuser.
-- Migrations still run as the bootstrap superuser: migration 002 re-asserts NOSUPERUSER on the
-- group roles and only a superuser may mention that attribute. This login owns the schema
-- objects through its group and serves purge and RAG indexing.
CREATE ROLE sus_explorer_admin  LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'migrator_password';
CREATE ROLE sus_explorer_ingest LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'ingest_password';
CREATE ROLE sus_explorer_hist   LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'history_password';
CREATE ROLE sus_explorer_app    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'reader_password';
GRANT sus_explorer_migrator TO sus_explorer_admin;
GRANT sus_explorer_runtime  TO sus_explorer_ingest;
GRANT sus_explorer_history  TO sus_explorer_hist;
GRANT sus_explorer_reader   TO sus_explorer_app;

GRANT CONNECT ON DATABASE :"DBNAME" TO sus_explorer_admin, sus_explorer_ingest, sus_explorer_hist, sus_explorer_app;
-- pgvector needs a superuser once.
CREATE EXTENSION IF NOT EXISTS vector;
SQL
