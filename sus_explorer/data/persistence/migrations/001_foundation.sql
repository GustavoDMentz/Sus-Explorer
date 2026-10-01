CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE datasus_ingestion_runs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source text NOT NULL CHECK (source = btrim(source) AND source <> ''),
    resource_type text NOT NULL CHECK (resource_type = btrim(resource_type) AND resource_type <> ''),
    source_resource_id text NOT NULL CHECK (source_resource_id = btrim(source_resource_id) AND source_resource_id <> ''),
    status text NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING', 'SUCCESS', 'PARTIAL', 'FAILED')),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    records_received bigint NOT NULL DEFAULT 0 CHECK (records_received >= 0),
    records_inserted bigint NOT NULL DEFAULT 0 CHECK (records_inserted >= 0),
    records_updated bigint NOT NULL DEFAULT 0 CHECK (records_updated >= 0),
    error_summary text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    CONSTRAINT ingestion_finish_matches_status CHECK (
        (status = 'RUNNING' AND finished_at IS NULL) OR
        (status <> 'RUNNING' AND finished_at IS NOT NULL)
    ),
    CONSTRAINT ingestion_time_order CHECK (finished_at IS NULL OR finished_at >= started_at),
    CONSTRAINT ingestion_counts_consistent CHECK (records_inserted + records_updated <= records_received),
    CONSTRAINT ingestion_success_has_no_error CHECK (status <> 'SUCCESS' OR error_summary IS NULL),
    CONSTRAINT ingestion_run_origin_unique UNIQUE (id, source, resource_type, source_resource_id)
);

CREATE TABLE datasus_raw_records (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source text NOT NULL CHECK (source = btrim(source) AND source <> ''),
    resource_type text NOT NULL CHECK (resource_type = btrim(resource_type) AND resource_type <> ''),
    source_resource_id text NOT NULL CHECK (source_resource_id = btrim(source_resource_id) AND source_resource_id <> ''),
    record_key text NOT NULL CHECK (record_key = btrim(record_key) AND record_key <> ''),
    external_id text CHECK (external_id IS NULL OR (external_id = btrim(external_id) AND external_id <> '')),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    fetched_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    first_ingestion_run_id bigint NOT NULL,
    last_change_run_id bigint NOT NULL,
    CONSTRAINT raw_source_record_unique UNIQUE (source, resource_type, source_resource_id, record_key),
    CONSTRAINT raw_first_run_origin FOREIGN KEY
        (first_ingestion_run_id, source, resource_type, source_resource_id)
        REFERENCES datasus_ingestion_runs (id, source, resource_type, source_resource_id)
        ON DELETE RESTRICT,
    CONSTRAINT raw_change_run_origin FOREIGN KEY
        (last_change_run_id, source, resource_type, source_resource_id)
        REFERENCES datasus_ingestion_runs (id, source, resource_type, source_resource_id)
        ON DELETE RESTRICT
);
CREATE INDEX raw_source_resource_page_idx
    ON datasus_raw_records (source, resource_type, id);
CREATE INDEX raw_external_id_idx ON datasus_raw_records (source, resource_type, external_id)
    WHERE external_id IS NOT NULL;

-- Only superseded payloads are copied; the current revision remains in raw_records.
CREATE TABLE datasus_raw_record_revisions (
    raw_record_id bigint NOT NULL REFERENCES datasus_raw_records(id) ON DELETE RESTRICT,
    revision bigint NOT NULL CHECK (revision > 0),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    external_id text,
    fetched_at timestamptz NOT NULL,
    change_run_id bigint NOT NULL REFERENCES datasus_ingestion_runs(id) ON DELETE RESTRICT,
    superseded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (raw_record_id, revision)
);

-- A source record can be observed once per run, including unchanged retries.
CREATE TABLE datasus_raw_record_observations (
    ingestion_run_id bigint NOT NULL REFERENCES datasus_ingestion_runs(id) ON DELETE RESTRICT,
    raw_record_id bigint NOT NULL REFERENCES datasus_raw_records(id) ON DELETE RESTRICT,
    revision bigint NOT NULL CHECK (revision > 0),
    fetched_at timestamptz NOT NULL,
    observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (ingestion_run_id, raw_record_id)
);

CREATE FUNCTION validate_raw_observation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM datasus_raw_records r
        JOIN datasus_ingestion_runs i ON i.id = NEW.ingestion_run_id
        WHERE r.id = NEW.raw_record_id
          AND (r.source, r.resource_type, r.source_resource_id) =
              (i.source, i.resource_type, i.source_resource_id)
          AND (r.revision = NEW.revision OR EXISTS (
              SELECT 1 FROM datasus_raw_record_revisions h
              WHERE h.raw_record_id = r.id AND h.revision = NEW.revision
          ))
    ) THEN
        RAISE EXCEPTION 'Observation origin or revision does not match raw record';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER raw_observation_valid BEFORE INSERT OR UPDATE
    ON datasus_raw_record_observations FOR EACH ROW
    EXECUTE FUNCTION validate_raw_observation();

CREATE FUNCTION archive_raw_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.source, NEW.resource_type, NEW.source_resource_id, NEW.record_key,
        NEW.created_at, NEW.first_ingestion_run_id)
       IS DISTINCT FROM
       (OLD.source, OLD.resource_type, OLD.source_resource_id, OLD.record_key,
        OLD.created_at, OLD.first_ingestion_run_id) THEN
        RAISE EXCEPTION 'Raw identity and first ingestion are immutable';
    END IF;
    IF NEW.payload IS NOT DISTINCT FROM OLD.payload
       AND NEW.external_id IS NOT DISTINCT FROM OLD.external_id THEN
        RAISE EXCEPTION 'Unchanged raw content must not be updated';
    END IF;
    INSERT INTO datasus_raw_record_revisions
        (raw_record_id, revision, payload, external_id, fetched_at, change_run_id)
    VALUES (OLD.id, OLD.revision, OLD.payload, OLD.external_id,
            OLD.fetched_at, OLD.last_change_run_id);
    NEW.revision := OLD.revision + 1;
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;
CREATE TRIGGER raw_revision_archive BEFORE UPDATE ON datasus_raw_records
    FOR EACH ROW EXECUTE FUNCTION archive_raw_revision();

CREATE TABLE immunization_records (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_record_id bigint NOT NULL UNIQUE REFERENCES datasus_raw_records(id) ON DELETE RESTRICT,
    source_revision bigint NOT NULL CHECK (source_revision > 0),
    vaccine_code text,
    dose_code text,
    application_date date,
    establishment_municipality_code text,
    establishment_uf text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT establishment_uf_format CHECK (
        establishment_uf IS NULL OR establishment_uf ~ '^[A-Z]{2}$'
    )
);
CREATE FUNCTION validate_immunization_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM datasus_raw_records
        WHERE id = NEW.source_record_id AND revision = NEW.source_revision
        FOR SHARE
    ) THEN
        RAISE EXCEPTION 'Immunization normalization must use the current raw revision';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER immunization_revision_valid BEFORE INSERT OR UPDATE
    ON immunization_records FOR EACH ROW
    EXECUTE FUNCTION validate_immunization_revision();
CREATE INDEX immunization_period_location_idx
    ON immunization_records (establishment_uf, establishment_municipality_code, application_date);
CREATE INDEX immunization_vaccine_dose_idx
    ON immunization_records (vaccine_code, dose_code);
