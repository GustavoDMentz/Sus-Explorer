-- Audit trail for administrative purges (docs/data-retention.md).
-- Append-only. Only the schema owner (migrator) can write; the app reads it so that a
-- purged partition is reported as unavailable, never as zero doses.
CREATE TABLE datasus_purge_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    purged_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    scope text NOT NULL CHECK (scope IN ('partition', 'old_revisions')),
    partition text CHECK (partition IS NULL OR partition ~ '^ano=[0-9]{4}/mes=(0[1-9]|1[0-2])/uf=[A-Z]{2}$'),
    older_than_days integer CHECK (older_than_days IS NULL OR older_than_days >= 1),
    dry_run boolean NOT NULL,
    reason text NOT NULL CHECK (char_length(reason) BETWEEN 10 AND 500),
    requested_by text NOT NULL DEFAULT session_user CHECK (char_length(requested_by) <= 128),
    counts jsonb NOT NULL CHECK (jsonb_typeof(counts) = 'object' AND pg_column_size(counts) <= 4096),
    CONSTRAINT purge_scope_target CHECK (
        (scope = 'partition' AND partition IS NOT NULL AND older_than_days IS NULL)
        OR (scope = 'old_revisions' AND partition IS NULL AND older_than_days IS NOT NULL))
);
CREATE INDEX datasus_purge_audit_partition_idx ON datasus_purge_audit (partition, purged_at DESC)
    WHERE NOT dry_run;
CREATE TRIGGER purge_audit_immutable
    BEFORE UPDATE OR DELETE ON datasus_purge_audit
    FOR EACH ROW EXECUTE FUNCTION reject_history_mutation();
REVOKE ALL ON datasus_purge_audit FROM PUBLIC;
ALTER TABLE datasus_purge_audit OWNER TO sus_explorer_migrator;
GRANT SELECT ON datasus_purge_audit TO sus_explorer_runtime, sus_explorer_reader;
