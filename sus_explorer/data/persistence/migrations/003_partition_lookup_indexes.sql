-- Exact monthly partition coverage and raw count lookup for the hybrid executor.
CREATE INDEX ingestion_runs_partition_latest_idx
    ON datasus_ingestion_runs (source, resource_type, source_resource_id, id DESC);

CREATE INDEX raw_records_partition_idx
    ON datasus_raw_records (source, resource_type, source_resource_id);
