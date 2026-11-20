-- Least-privilege split for deployments with separate logins (docs/postgres-roles.md).
--
-- 1. sus_explorer_history: a narrow group for the opt-in query/result history. The app
--    writes history, but must not hold the ingestion role (which can modify raw records)
--    and the reader must stay read-only.
-- 2. The RAG tables created by migration 007 had no owner or grants: give them the
--    schema owner and let the reader search them.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sus_explorer_history') THEN
        CREATE ROLE sus_explorer_history NOLOGIN NOINHERIT NOSUPERUSER
            NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
END
$$;
ALTER ROLE sus_explorer_history NOLOGIN NOINHERIT NOSUPERUSER
    NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
REVOKE sus_explorer_migrator, sus_explorer_runtime, sus_explorer_reader FROM sus_explorer_history;
REVOKE sus_explorer_history FROM sus_explorer_runtime, sus_explorer_reader;

ALTER TABLE knowledge_documents OWNER TO sus_explorer_migrator;
ALTER TABLE knowledge_chunks OWNER TO sus_explorer_migrator;
ALTER TABLE knowledge_indexing_attempts OWNER TO sus_explorer_migrator;
REVOKE ALL ON knowledge_documents, knowledge_chunks, knowledge_indexing_attempts FROM PUBLIC;
GRANT SELECT ON knowledge_documents, knowledge_chunks TO sus_explorer_reader;

DO $$
DECLARE
    schema_name text := current_schema();
BEGIN
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO sus_explorer_history', schema_name);
    EXECUTE format('GRANT SELECT, INSERT ON %I.query_history TO sus_explorer_history', schema_name);
    EXECUTE format('GRANT SELECT, INSERT ON %I.analytical_queries TO sus_explorer_history', schema_name);
    EXECUTE format(
        'GRANT SELECT, INSERT, UPDATE (last_seen_at, observations) ON %I.analytical_result_versions '
        'TO sus_explorer_history', schema_name);
END
$$;
