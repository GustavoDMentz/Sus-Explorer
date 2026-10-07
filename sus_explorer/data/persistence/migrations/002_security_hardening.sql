-- Establish a database-enforced trust boundary around operational persistence.
-- These are structural NOLOGIN roles. Deployment-specific login roles receive
-- membership in exactly one of runtime or reader; only the migration principal
-- may receive membership in the owner role.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sus_explorer_migrator') THEN
        CREATE ROLE sus_explorer_migrator NOLOGIN NOINHERIT NOSUPERUSER
            NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sus_explorer_runtime') THEN
        CREATE ROLE sus_explorer_runtime NOLOGIN NOINHERIT NOSUPERUSER
            NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sus_explorer_reader') THEN
        CREATE ROLE sus_explorer_reader NOLOGIN NOINHERIT NOSUPERUSER
            NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
END
$$;

ALTER ROLE sus_explorer_migrator NOLOGIN NOINHERIT NOSUPERUSER
    NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE sus_explorer_runtime NOLOGIN NOINHERIT NOSUPERUSER
    NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE sus_explorer_reader NOLOGIN NOINHERIT NOSUPERUSER
    NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

REVOKE sus_explorer_migrator FROM sus_explorer_runtime, sus_explorer_reader;
REVOKE sus_explorer_runtime FROM sus_explorer_reader;

ALTER TABLE datasus_ingestion_runs
    ADD CONSTRAINT ingestion_source_size CHECK (char_length(source) <= 128),
    ADD CONSTRAINT ingestion_resource_type_size CHECK (char_length(resource_type) <= 128),
    ADD CONSTRAINT ingestion_resource_id_size CHECK (char_length(source_resource_id) <= 1024),
    ADD CONSTRAINT ingestion_error_summary_size CHECK (char_length(error_summary) <= 2048),
    ADD CONSTRAINT ingestion_metadata_size CHECK (pg_column_size(metadata) <= 262144);

ALTER TABLE datasus_raw_records
    ADD CONSTRAINT raw_source_size CHECK (char_length(source) <= 128),
    ADD CONSTRAINT raw_resource_type_size CHECK (char_length(resource_type) <= 128),
    ADD CONSTRAINT raw_resource_id_size CHECK (char_length(source_resource_id) <= 1024),
    ADD CONSTRAINT raw_record_key_size CHECK (char_length(record_key) <= 1024),
    ADD CONSTRAINT raw_external_id_size CHECK (char_length(external_id) <= 1024),
    ADD CONSTRAINT raw_payload_size CHECK (pg_column_size(payload) <= 4194304);

ALTER TABLE immunization_records
    ADD CONSTRAINT immunization_vaccine_code_size CHECK (char_length(vaccine_code) <= 256),
    ADD CONSTRAINT immunization_dose_code_size CHECK (char_length(dose_code) <= 256),
    ADD CONSTRAINT immunization_municipality_size
        CHECK (char_length(establishment_municipality_code) <= 16);

-- PUBLIC must not create objects beside trusted relations or invoke internal
-- trigger functions directly.
DO $$
DECLARE
    schema_name text := current_schema();
    function_name text;
BEGIN
    EXECUTE format('REVOKE CREATE ON SCHEMA %I FROM PUBLIC', schema_name);
    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM PUBLIC', schema_name);
    EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA %I FROM PUBLIC', schema_name);
    EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA %I FROM PUBLIC', schema_name);

    FOREACH function_name IN ARRAY ARRAY[
        'validate_new_raw_record',
        'reject_history_mutation',
        'require_running_ingestion',
        'validate_raw_observation',
        'archive_raw_revision',
        'remove_stale_immunization',
        'validate_immunization_revision',
        'protect_ingestion_run'
    ] LOOP
        EXECUTE format(
            'ALTER FUNCTION %I.%I() OWNER TO sus_explorer_migrator',
            schema_name, function_name
        );
        EXECUTE format(
            'ALTER FUNCTION %I.%I() SECURITY DEFINER',
            schema_name, function_name
        );
        EXECUTE format(
            'ALTER FUNCTION %I.%I() SET search_path = %I, pg_catalog',
            schema_name, function_name, schema_name
        );
    END LOOP;

    EXECUTE format('ALTER TABLE %I.schema_migrations OWNER TO sus_explorer_migrator', schema_name);
    EXECUTE format('ALTER TABLE %I.datasus_ingestion_runs OWNER TO sus_explorer_migrator', schema_name);
    EXECUTE format('ALTER TABLE %I.datasus_raw_records OWNER TO sus_explorer_migrator', schema_name);
    EXECUTE format('ALTER TABLE %I.datasus_raw_record_revisions OWNER TO sus_explorer_migrator', schema_name);
    EXECUTE format('ALTER TABLE %I.datasus_raw_record_observations OWNER TO sus_explorer_migrator', schema_name);
    EXECUTE format('ALTER TABLE %I.immunization_records OWNER TO sus_explorer_migrator', schema_name);
    EXECUTE format('ALTER SCHEMA %I OWNER TO sus_explorer_migrator', schema_name);

    EXECUTE format('GRANT USAGE ON SCHEMA %I TO sus_explorer_runtime, sus_explorer_reader', schema_name);
    EXECUTE format(
        'GRANT SELECT, INSERT, UPDATE ON %I.datasus_ingestion_runs TO sus_explorer_runtime',
        schema_name
    );
    EXECUTE format(
        'GRANT SELECT, INSERT, UPDATE ON %I.datasus_raw_records TO sus_explorer_runtime',
        schema_name
    );
    EXECUTE format(
        'GRANT SELECT, INSERT ON %I.datasus_raw_record_observations TO sus_explorer_runtime',
        schema_name
    );
    EXECUTE format(
        'GRANT SELECT, INSERT, UPDATE ON %I.immunization_records TO sus_explorer_runtime',
        schema_name
    );
    EXECUTE format(
        'GRANT SELECT ON %I.datasus_raw_record_revisions TO sus_explorer_runtime',
        schema_name
    );
    EXECUTE format(
        'GRANT SELECT ON %I.datasus_ingestion_runs, %I.datasus_raw_records, '
        '%I.datasus_raw_record_revisions, %I.datasus_raw_record_observations, '
        '%I.immunization_records TO sus_explorer_reader',
        schema_name, schema_name, schema_name, schema_name, schema_name
    );
    EXECUTE format(
        'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO sus_explorer_runtime',
        schema_name
    );

    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE sus_explorer_migrator IN SCHEMA %I '
        'REVOKE ALL ON TABLES FROM PUBLIC', schema_name
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE sus_explorer_migrator IN SCHEMA %I '
        'REVOKE ALL ON SEQUENCES FROM PUBLIC', schema_name
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE sus_explorer_migrator IN SCHEMA %I '
        'REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC', schema_name
    );
END
$$;
