-- Metadata only: neither questions nor result payloads are stored here.
CREATE TABLE query_history (
    id uuid PRIMARY KEY,
    executed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    operation text NOT NULL CHECK (operation IN ('count', 'group', 'timeseries', 'latency', 'temporal')),
    parameters jsonb NOT NULL CHECK (jsonb_typeof(parameters) = 'object' AND pg_column_size(parameters) <= 4096),
    executor text NOT NULL CHECK (executor IN ('r2', 'postgres', 'unknown')),
    status text NOT NULL CHECK (status IN ('SUCCESS', 'FAILED')),
    duration_ms bigint NOT NULL CHECK (duration_ms >= 0),
    provenance jsonb NOT NULL CHECK (jsonb_typeof(provenance) = 'object' AND pg_column_size(provenance) <= 8192),
    result_ref text CHECK (result_ref IS NULL OR char_length(result_ref) <= 256)
);
CREATE INDEX query_history_recent_idx ON query_history (executed_at DESC, id DESC);
REVOKE ALL ON query_history FROM PUBLIC;
ALTER TABLE query_history OWNER TO sus_explorer_migrator;
GRANT SELECT, INSERT ON query_history TO sus_explorer_runtime;
GRANT SELECT ON query_history TO sus_explorer_reader;
