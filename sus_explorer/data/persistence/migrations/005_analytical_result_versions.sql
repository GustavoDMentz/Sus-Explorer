-- Versioned analytical results, distinct from operational query_history.
CREATE TABLE analytical_queries (
    query_key char(64) PRIMARY KEY,
    plan jsonb NOT NULL CHECK (jsonb_typeof(plan) = 'object' AND pg_column_size(plan) <= 8192),
    semantics_version integer NOT NULL CHECK (semantics_version > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE analytical_result_versions (
    query_key char(64) NOT NULL REFERENCES analytical_queries(query_key),
    version integer NOT NULL CHECK (version > 0),
    result_hash char(64) NOT NULL,
    result_data jsonb NOT NULL CHECK (jsonb_typeof(result_data) = 'object' AND pg_column_size(result_data) <= 1048576),
    first_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    last_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    observations bigint NOT NULL DEFAULT 1 CHECK (observations > 0),
    PRIMARY KEY (query_key, version),
    CHECK (last_seen_at >= first_seen_at)
);
CREATE INDEX analytical_result_versions_recent_idx
    ON analytical_result_versions (last_seen_at DESC);
REVOKE ALL ON analytical_queries, analytical_result_versions FROM PUBLIC;
ALTER TABLE analytical_queries OWNER TO sus_explorer_migrator;
ALTER TABLE analytical_result_versions OWNER TO sus_explorer_migrator;
GRANT SELECT, INSERT ON analytical_queries TO sus_explorer_runtime;
GRANT SELECT, INSERT, UPDATE (last_seen_at, observations) ON analytical_result_versions TO sus_explorer_runtime;
GRANT SELECT ON analytical_queries, analytical_result_versions TO sus_explorer_reader;
