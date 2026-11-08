-- The runtime resolves completed monthly/UF partitions without consulting R2.
CREATE INDEX ingestion_runs_analytical_partition_idx
    ON datasus_ingestion_runs ((metadata->>'partition'), id DESC)
    WHERE resource_type = 'immunization';
