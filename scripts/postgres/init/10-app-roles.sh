#!/usr/bin/env bash
# Creates the dedicated login profiles on first start and supports controlled recovery
# after a failed initdb script. Passwords are supplied by Compose from the untracked .env.
set -euo pipefail

for name in POSTGRES_MIGRATOR_PASSWORD POSTGRES_INGEST_PASSWORD POSTGRES_HISTORY_PASSWORD POSTGRES_READER_PASSWORD; do
  if [ -z "${!name:-}" ]; then
    echo "ERRO: $name não definida; veja .env.example" >&2
    exit 1
  fi
done

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v DBNAME="$POSTGRES_DB" \
  -v migrator_password="$POSTGRES_MIGRATOR_PASSWORD" \
  -v ingest_password="$POSTGRES_INGEST_PASSWORD" \
  -v history_password="$POSTGRES_HISTORY_PASSWORD" \
  -v reader_password="$POSTGRES_READER_PASSWORD" <<'SQL'
-- Structural groups; reassert safe attributes even on a partially initialized cluster.
SELECT format('CREATE ROLE %I NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', role_name)
FROM unnest(ARRAY['sus_explorer_migrator','sus_explorer_runtime','sus_explorer_reader','sus_explorer_history']) AS role_name
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name)
\gexec

ALTER ROLE sus_explorer_migrator NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE sus_explorer_runtime  NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE sus_explorer_reader   NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE sus_explorer_history  NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

-- Create missing logins, then converge existing logins to the configured password and
-- restricted attributes. Password values are emitted only as SQL literals, never logged.
SELECT format('CREATE ROLE %I LOGIN INHERIT %s NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L', role_name,
  CASE WHEN role_name = 'sus_explorer_admin' THEN 'SUPERUSER' ELSE 'NOSUPERUSER' END,
  password_value)
FROM (VALUES
  ('sus_explorer_admin', :'migrator_password'),
  ('sus_explorer_ingest', :'ingest_password'),
  ('sus_explorer_hist', :'history_password'),
  ('sus_explorer_app', :'reader_password')
) AS credentials(role_name, password_value)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name)
\gexec

-- Immutable migration 002 explicitly sets role attributes and requires SUPERUSER.
-- This login is supplied only to the migrate and document-index preparation services.
ALTER ROLE sus_explorer_admin  LOGIN INHERIT SUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'migrator_password';
ALTER ROLE sus_explorer_ingest LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'ingest_password';
ALTER ROLE sus_explorer_hist   LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'history_password';
ALTER ROLE sus_explorer_app    LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'reader_password';

-- Converge each login to exactly its intended structural profile.
SELECT format('REVOKE %I FROM %I', membership.role_name, membership.login_name)
FROM (VALUES
  ('sus_explorer_migrator', 'sus_explorer_admin'),
  ('sus_explorer_runtime', 'sus_explorer_ingest'),
  ('sus_explorer_history', 'sus_explorer_hist'),
  ('sus_explorer_reader', 'sus_explorer_app')
) AS intended(role_name, login_name)
JOIN LATERAL (
  SELECT roles.rolname AS role_name, logins.rolname AS login_name
  FROM pg_auth_members memberships
  JOIN pg_roles roles ON roles.oid = memberships.roleid
  JOIN pg_roles logins ON logins.oid = memberships.member
  WHERE logins.rolname = intended.login_name
    AND roles.rolname IN ('sus_explorer_migrator','sus_explorer_runtime','sus_explorer_reader','sus_explorer_history')
    AND roles.rolname <> intended.role_name
) AS membership ON true
\gexec
GRANT sus_explorer_migrator TO sus_explorer_admin;
GRANT sus_explorer_runtime  TO sus_explorer_ingest;
GRANT sus_explorer_history  TO sus_explorer_hist;
GRANT sus_explorer_reader   TO sus_explorer_app;

GRANT CONNECT ON DATABASE :"DBNAME" TO sus_explorer_admin, sus_explorer_ingest, sus_explorer_hist, sus_explorer_app;
CREATE EXTENSION IF NOT EXISTS vector;
SQL
