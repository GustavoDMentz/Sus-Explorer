"""Opt-in invariants against a disposable PostgreSQL database with pgvector."""

from __future__ import annotations

import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from sus_explorer.data.persistence.database import connect
from sus_explorer.data.persistence.healthcheck import check_postgres
from sus_explorer.data.persistence.history import record_query, recent_queries
from sus_explorer.data.persistence.migrate import MIGRATIONS, migrate
from sus_explorer.data.persistence.repositories import (
    ImmunizationProjection,
    IngestionRunRepository,
    OperationalPersistence,
    RawRecordRepository,
)
from sus_explorer.pni import QueryResult
from sus_explorer.postgres_executor import PostgresQueryExecutor
from sus_explorer.data.persistence.ingest_csv import ingest_csv
from sus_explorer.schemas import QueryPlan
from sus_explorer.data.persistence.history import safe_provenance


pytestmark = pytest.mark.skipif(
    os.getenv("SUS_EXPLORER_TEST_DB") != "1",
    reason="Set SUS_EXPLORER_TEST_DB=1 with a disposable PostgreSQL database",
)


@pytest.fixture
def database():
    schema = "foundation_test_" + uuid4().hex
    with connect() as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        connection.commit()
        try:
            connection.execute(
                sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema))
            )
            connection.commit()
            yield connection, schema
        finally:
            connection.rollback()
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )
            connection.commit()


def rejected(connection, statement, values=()):
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            connection.execute(statement, values)


def test_postgres_executor_uses_completed_partition_without_r2(database, monkeypatch):
    connection, schema = database
    migrate(connection, schema=schema)
    connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
    connection.commit()
    runs = IngestionRunRepository(connection)
    run = runs.start(source="official-test", resource_type="immunization",
                     source_resource_id="2026/05/RS", metadata={"partition": "ano=2026/mes=05/uf=RS", "source_rows": 3})
    connection.commit()
    persistence = OperationalPersistence(connection)
    for index, sex in enumerate(("F", "F", "M")):
        persistence.save_immunization(
            source="official-test", resource_type="immunization", source_resource_id="2026/05/RS",
            record_key=f"record-{index}", payload={"tp_sexo_paciente": sex,
                "dt_entrada_rnds": "2026-05-03", "no_municipio_estabelecimento": "PORTO ALEGRE",
                "nu_idade_paciente": "30", "sg_imunobiologico": "INFLUENZA"},
            fetched_at=datetime.now(timezone.utc), ingestion_run_id=run["id"],
            projection=ImmunizationProjection(vaccine_code="9", application_date=date(2026, 5, 1),
                establishment_municipality_code="4314902", establishment_uf="RS"))
    runs.finish(run["id"], status="SUCCESS", records_received=3, records_inserted=3, records_updated=0)
    connection.commit()
    monkeypatch.setenv("POSTGRES_SCHEMA", schema)
    executor = PostgresQueryExecutor()
    base = {"year": 2026, "month": 5, "uf": "RS"}
    assert executor.execute(QueryPlan(operation="count", **base)).data == {"doses": 3}
    assert executor.execute(QueryPlan(operation="count", sex="F", **base)).data == {"doses": 2}
    assert executor.execute(QueryPlan(operation="group", group_by="sex", **base)).data["total_after_filters"] == 3
    assert executor.execute(QueryPlan(operation="latency", **base)).data["n_valid"] == 3
    assert executor.execute(QueryPlan(operation="timeseries", uf="RS", start_year=2026,
        start_month=5, end_year=2026, end_month=5)).data["rows"] == [{"period": "2026-05", "doses": 3}]
    with pytest.raises(FileNotFoundError):
        executor.execute(QueryPlan(operation="count", year=2026, month=6, uf="RS"))


def test_streaming_csv_import_is_idempotent(database, tmp_path, monkeypatch):
    connection, schema = database
    migrate(connection, schema=schema)
    connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
    connection.commit()
    source = tmp_path / "official_shape.csv"
    source.write_text("co_documento,co_vacina,dt_vacina,co_municipio_estabelecimento,sg_uf_estabelecimento,tp_sexo_paciente\n"
                      "doc-a,9,2026-05-01,4314902,RS,F\n"
                      "doc-b,9,2026-05-02,4314902,RS,M\n", encoding="utf-8")
    first = ingest_csv(source, year=2026, month=5, uf="RS", resource_id="official-test-resource",
                       connection=connection, batch_size=1)
    second = ingest_csv(source, year=2026, month=5, uf="RS", resource_id="official-test-resource",
                        connection=connection, batch_size=1)
    assert first["status"] == "SUCCESS" and first["records_received"] == 2
    assert second["id"] == first["id"]
    monkeypatch.setenv("POSTGRES_SCHEMA", schema)
    result = PostgresQueryExecutor().execute(QueryPlan(operation="count", year=2026, month=5, uf="RS"))
    assert result.data == {"doses": 2}


def test_official_zip_import_filters_selected_uf_without_extraction(database, tmp_path):
    connection, schema = database
    migrate(connection, schema=schema)
    connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
    connection.commit()
    archive_path = tmp_path / "national.csv.zip"
    content = ("co_documento;co_vacina;dt_vacina;co_municipio_estabelecimento;sg_uf_estabelecimento\n"
               "ac-1;9;2026-01-05;1200401;AC\n"
               "rs-1;9;2026-01-05;4314902;RS\n")
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("vacinacao_jan_2026.csv", content.encode("latin-1"))
    run = ingest_csv(archive_path, year=2026, month=1, uf="AC",
                     resource_id="official-zip-test", encoding="latin-1", delimiter=";",
                     connection=connection)
    assert run["status"] == "SUCCESS" and run["records_received"] == 1
    assert connection.execute("SELECT count(*) AS n FROM datasus_raw_records").fetchone()["n"] == 1
    assert connection.execute("SELECT payload->>'co_documento' AS id FROM datasus_raw_records").fetchone()["id"] == "ac-1"


def test_interrupted_import_leaves_an_orphan_that_the_next_import_closes(database, tmp_path, monkeypatch):
    connection, schema = database
    migrate(connection, schema=schema)
    connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
    connection.commit()
    source = tmp_path / "resume.csv"
    source.write_text("co_documento,co_vacina,dt_vacina,co_municipio_estabelecimento,sg_uf_estabelecimento\n"
                      "doc-a,9,2026-05-01,4314902,RS\n"
                      "doc-b,9,2026-05-02,4314902,RS\n", encoding="utf-8")
    from sus_explorer.data.persistence import ingest_csv as csv_module
    original = csv_module.OperationalPersistence.save_immunization
    calls = 0

    def interrupt_second(self, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt()
        return original(self, **kwargs)

    monkeypatch.setattr(csv_module.OperationalPersistence, "save_immunization", interrupt_second)
    with pytest.raises(KeyboardInterrupt):
        ingest_csv(source, year=2026, month=5, uf="RS", resource_id="resume-resource",
                   connection=connection, batch_size=1)
    pending = connection.execute("SELECT id,status FROM datasus_ingestion_runs").fetchone()
    assert pending["status"] == "RUNNING"
    monkeypatch.setattr(csv_module.OperationalPersistence, "save_immunization", original)
    resumed = ingest_csv(source, year=2026, month=5, uf="RS", resource_id="resume-resource",
                         connection=connection, batch_size=1)
    # The interrupted snapshot was one transaction: nothing of it survived. The next import
    # closes the orphan (nobody holds its lock) and starts a fresh run.
    assert resumed["id"] != pending["id"] and resumed["status"] == "SUCCESS"
    closed = connection.execute("SELECT status, error_summary FROM datasus_ingestion_runs WHERE id=%s",
                                (pending["id"],)).fetchone()
    assert closed["status"] == "FAILED" and "Orphaned" in closed["error_summary"]
    assert connection.execute("SELECT count(*) AS n FROM datasus_raw_records").fetchone()["n"] == 2


def test_knowledge_vector_cosine_and_foreign_key(database):
    connection, schema = database
    migrate(connection, schema=schema)
    extension = connection.execute("""SELECT n.nspname AS name FROM pg_extension e
        JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='vector'""").fetchone()["name"]
    connection.execute(sql.SQL("SET search_path TO {}, {}, public").format(
        sql.Identifier(schema), sql.Identifier(extension)))
    connection.commit()
    with connection.transaction():
        doc = connection.execute("""INSERT INTO knowledge_documents
            (title, source, source_type, original_reference, content_hash, embedding_model)
            VALUES ('Guia', 'project_docs', 'markdown', 'guide.md', %s, 'model-a')
            RETURNING id""", ("a" * 64,)).fetchone()["id"]
        first = "[1," + ",".join(["0"] * 1023) + "]"
        second = "[0,1," + ",".join(["0"] * 1022) + "]"
        for index, vector in enumerate((first, second)):
            connection.execute("""INSERT INTO knowledge_chunks
                (document_id,chunk_index,content,embedding,token_count,embedding_model)
                VALUES (%s,%s,%s,%s::vector,2,'model-a')""",
                (doc, index, f"trecho {index}", vector))
    rows = connection.execute("""SELECT chunk_index, 1-(embedding <=> %s::vector) AS score
        FROM knowledge_chunks WHERE embedding_model='model-a'
        ORDER BY embedding <=> %s::vector""", (first, first)).fetchall()
    assert [row["chunk_index"] for row in rows] == [0, 1]
    assert rows[0]["score"] == pytest.approx(1)
    rejected(connection, "INSERT INTO knowledge_chunks (document_id,chunk_index,content,embedding,token_count,embedding_model) VALUES (999999,0,'x',%s::vector,1,'model-a')", (first,))


def test_health_and_query_history_survive_new_connection(database):
    connection, schema = database
    assert check_postgres()
    migrate(connection, schema=schema)
    query_id = uuid4()
    plan = QueryPlan(operation="count", year=2026, month=5, uf="RS",
                     vaccine_text="texto livre omitido")
    result = QueryResult("count", {"doses": 3}, {
        "source": "R2", "period": "2026-05",
        "partitions": ["ano=2026/mes=05/uf=RS"],
    })
    record_query(query_id=query_id, plan=plan, executor="r2", status="SUCCESS",
                 duration_ms=25, provenance=safe_provenance(result), connection=connection)
    connection.commit()
    with connect() as reopened:
        reopened.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
        rows = recent_queries(connection=reopened)
        assert len(rows) == 1
        assert rows[0]["id"] == query_id
        assert rows[0]["executor"] == "r2"
        assert rows[0]["parameters"]["year"] == 2026
        assert "vaccine_text" not in rows[0]["parameters"]
        assert "doses" not in rows[0]["provenance"]


def test_atomic_raw_normalization_history_and_completion(database):
    connection, _ = database
    schema = database[1]
    assert migrate(connection, schema=schema) == [
        "001_foundation.sql",
        "002_security_hardening.sql",
        "003_partition_lookup_indexes.sql",
        "004_query_history.sql",
        "005_analytical_result_versions.sql",
        "006_immutable_source_fingerprint.sql",
        "007_knowledge_rag.sql",
        "008_postgres_analytical_lookup.sql",
    ]
    assert migrate(connection, schema=schema) == []

    runs = IngestionRunRepository(connection)
    operational = OperationalPersistence(connection)
    first = runs.start(
        source="synthetic",
        resource_type="immunization",
        source_resource_id="resource-1",
        metadata={"source_sha256": "abc123", "source_url": "https://example.invalid"},
    )
    base = dict(
        source="synthetic",
        resource_type="immunization",
        source_resource_id="resource-1",
        record_key="row-1",
    )
    t1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    raw, normalized = operational.save_immunization(
        **base,
        payload={"co_vacina": "33"},
        fetched_at=t1,
        ingestion_run_id=first["id"],
        projection=ImmunizationProjection(
            vaccine_code="33",
            dose_code="1",
            application_date=date(2025, 1, 2),
            establishment_municipality_code="4314902",
            establishment_uf="RS",
        ),
    )
    assert raw["revision"] == normalized["source_revision"] == 1

    second = runs.start(
        source="synthetic",
        resource_type="immunization",
        source_resource_id="resource-1",
    )
    changed, normalized2 = operational.save_immunization(
        **base,
        payload={"co_vacina": "34"},
        fetched_at=t1 + timedelta(days=1),
        ingestion_run_id=second["id"],
        projection=ImmunizationProjection(
            vaccine_code="34", establishment_uf="RS"
        ),
    )
    assert changed["revision"] == normalized2["source_revision"] == 2
    assert connection.execute(
        "SELECT count(*) AS n FROM datasus_raw_record_revisions"
    ).fetchone()["n"] == 1
    current = connection.execute(
        "SELECT i.source_revision, r.revision FROM immunization_records i "
        "JOIN datasus_raw_records r ON r.id = i.source_record_id"
    ).fetchone()
    assert current["source_revision"] == current["revision"] == 2

    rejected(connection, "UPDATE datasus_raw_record_revisions SET revision = 9")
    rejected(connection, "DELETE FROM datasus_raw_record_revisions")
    rejected(connection, "UPDATE datasus_raw_record_observations SET revision = 9")
    rejected(connection, "DELETE FROM datasus_raw_record_observations")

    finished = runs.finish(
        first["id"],
        status="SUCCESS",
        records_received=1,
        records_inserted=1,
        records_updated=0,
    )
    assert finished["metadata"]["source_sha256"] == "abc123"
    rejected(connection, "UPDATE datasus_ingestion_runs SET metadata = '{}' WHERE id = %s", (first["id"],))
    rejected(connection, "DELETE FROM datasus_ingestion_runs WHERE id = %s", (first["id"],))


def test_failed_projection_rolls_back_raw_change(database):
    connection, schema = database
    migrate(connection, schema=schema)
    run = IngestionRunRepository(connection).start(
        source="synthetic", resource_type="immunization", source_resource_id="resource"
    )
    with pytest.raises(psycopg.Error):
        OperationalPersistence(connection).save_immunization(
            source="synthetic",
            resource_type="immunization",
            source_resource_id="resource",
            record_key="bad-row",
            payload={"sensitive": "must-not-be-logged"},
            fetched_at=datetime.now(timezone.utc),
            ingestion_run_id=run["id"],
            projection=ImmunizationProjection(establishment_uf="rs"),
        )
    assert RawRecordRepository(connection).list_records("synthetic", "immunization") == []


def test_failed_migration_rolls_back_and_checksum_is_enforced(database, tmp_path):
    connection, schema = database
    (tmp_path / "001_foundation.sql").write_bytes(
        (MIGRATIONS / "001_foundation.sql").read_bytes()
    )
    (tmp_path / "002_invalid.sql").write_text(
        "CREATE TABLE should_rollback (id integer); SELECT 1 / 0;",
        encoding="utf-8",
    )
    with pytest.raises(psycopg.Error):
        migrate(connection, tmp_path, schema=schema)
    assert connection.execute(
        "SELECT count(*) AS n FROM information_schema.tables WHERE table_schema = %s",
        (schema,),
    ).fetchone()["n"] == 0

    (tmp_path / "002_invalid.sql").unlink()
    assert migrate(connection, tmp_path, schema=schema) == ["001_foundation.sql"]
    (tmp_path / "001_foundation.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(RuntimeError, match="changed after application"):
        migrate(connection, tmp_path, schema=schema)


def test_concurrent_migrations_are_serialized(database):
    connection, schema = database

    def apply_once():
        with connect() as other:
            other.execute(
                sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema))
            )
            other.commit()
            return migrate(other, schema=schema)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: apply_once(), range(2)))
    assert sorted(results, key=len) == [
        [],
        ["001_foundation.sql", "002_security_hardening.sql", "003_partition_lookup_indexes.sql",
         "004_query_history.sql", "005_analytical_result_versions.sql",
         "006_immutable_source_fingerprint.sql", "007_knowledge_rag.sql", "008_postgres_analytical_lookup.sql"],
    ]


@pytest.fixture
def secured_database(database):
    admin, schema = database
    migrate(admin, schema=schema)
    suffix = uuid4().hex
    runtime_login = "runtime_" + suffix
    reader_login = "reader_" + suffix
    password = "disposable-role-password"
    for login, group in (
        (runtime_login, "sus_explorer_runtime"),
        (reader_login, "sus_explorer_reader"),
    ):
        admin.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(login), sql.Literal(password)
            )
        )
        admin.execute(
            sql.SQL("GRANT {} TO {}").format(
                sql.Identifier(group), sql.Identifier(login)
            )
        )
    admin.commit()

    def role_connection(user):
        return psycopg.connect(
            host=os.environ["POSTGRES_HOST"],
            port=os.environ["POSTGRES_PORT"],
            dbname=os.environ["POSTGRES_DB"],
            user=user,
            password=password,
            options=f"-c search_path={schema},pg_catalog",
            row_factory=dict_row,
        )

    try:
        with role_connection(runtime_login) as runtime, role_connection(
            reader_login
        ) as reader:
            yield admin, runtime, reader, schema
    finally:
        admin.rollback()
        for login in (runtime_login, reader_login):
            admin.execute(
                sql.SQL("DROP OWNED BY {} CASCADE").format(sql.Identifier(login))
            )
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(login)))
        admin.commit()


def test_runtime_and_reader_least_privilege(secured_database):
    _, runtime, reader, _ = secured_database
    denied_runtime = (
        "DROP TABLE datasus_raw_records",
        "ALTER TABLE datasus_raw_records ADD COLUMN compromised text",
        "ALTER TABLE datasus_raw_records DISABLE TRIGGER ALL",
        "CREATE TABLE attacker_table (id integer)",
        "CREATE FUNCTION attacker_function() RETURNS integer LANGUAGE sql AS 'SELECT 1'",
        "SET ROLE sus_explorer_migrator",
        "UPDATE datasus_raw_record_revisions SET revision = 99",
        "DELETE FROM datasus_raw_record_revisions",
        "UPDATE datasus_raw_record_observations SET revision = 99",
        "DELETE FROM datasus_raw_record_observations",
    )
    for statement in denied_runtime:
        rejected(runtime, statement)

    assert reader.execute("SELECT count(*) AS n FROM datasus_raw_records").fetchone()["n"] == 0
    assert reader.execute("SELECT count(*) AS n FROM query_history").fetchone()["n"] == 0
    record_query(query_id=uuid4(), plan=QueryPlan(operation="count", year=2026, uf="RS"),
                 executor="r2", status="SUCCESS", duration_ms=1, connection=runtime)
    assert reader.execute("SELECT count(*) AS n FROM query_history").fetchone()["n"] == 1
    rejected(runtime, "UPDATE query_history SET status = 'FAILED'")
    rejected(runtime, "DELETE FROM query_history")
    for statement in (
        "INSERT INTO datasus_ingestion_runs (source, resource_type, source_resource_id) VALUES ('x','y','z')",
        "UPDATE datasus_ingestion_runs SET records_received = 1",
        "DELETE FROM datasus_ingestion_runs",
        "CREATE TABLE reader_table (id integer)",
    ):
        rejected(reader, statement)



def test_runtime_cannot_rewrite_historical_fingerprint(secured_database):
    """Exercise actual runtime-role SQL permissions after migration 006."""
    _, runtime, _, _ = secured_database
    assert runtime.execute(
        "SELECT has_column_privilege(current_user, "
        "'analytical_result_versions', 'source_fingerprint', 'UPDATE') AS allowed"
    ).fetchone()["allowed"] is False
    rejected(
        runtime,
        "UPDATE analytical_result_versions "
        "SET source_fingerprint = source_fingerprint WHERE false",
    )
    assert runtime.execute(
        "SELECT has_column_privilege(current_user, "
        "'analytical_result_versions', 'observations', 'UPDATE') AS allowed"
    ).fetchone()["allowed"] is True
    runtime.execute(
        "UPDATE analytical_result_versions "
        "SET observations = observations WHERE false"
    )



def test_runtime_authorized_flow_and_finished_run_guards(secured_database):
    _, runtime, _, _ = secured_database
    runs = IngestionRunRepository(runtime)
    persistence = OperationalPersistence(runtime)
    run = runs.start(
        source="synthetic",
        resource_type="immunization",
        source_resource_id="resource-1",
        metadata={"checksum": "abc123"},
    )
    raw, normalized = persistence.save_immunization(
        source="synthetic",
        resource_type="immunization",
        source_resource_id="resource-1",
        record_key="row-1",
        payload={"co_vacina": "33"},
        fetched_at=datetime.now(timezone.utc),
        ingestion_run_id=run["id"],
        projection=ImmunizationProjection(vaccine_code="33", establishment_uf="RS"),
    )
    assert raw["revision"] == normalized["source_revision"] == 1
    runs.finish(
        run["id"],
        status="SUCCESS",
        records_received=1,
        records_inserted=1,
        records_updated=0,
    )
    rejected(
        runtime,
        "UPDATE datasus_ingestion_runs SET records_received = 2 WHERE id = %s",
        (run["id"],),
    )
    rejected(
        runtime,
        "INSERT INTO datasus_raw_record_observations "
        "(ingestion_run_id, raw_record_id, revision, fetched_at) "
        "VALUES (%s, %s, %s, clock_timestamp())",
        (run["id"], raw["id"], raw["revision"]),
    )


def test_database_constraints_and_error_sanitization(secured_database, monkeypatch):
    _, runtime, _, _ = secured_database
    with pytest.raises(psycopg.Error):
        with runtime.transaction():
            runtime.execute(
                "INSERT INTO datasus_ingestion_runs "
                "(source, resource_type, source_resource_id) VALUES (%s, 'x', 'y')",
                ("x" * 129,),
            )

    run_for_payload = IngestionRunRepository(runtime).start(
        source="synthetic",
        resource_type="immunization",
        source_resource_id="oversized-payload",
    )
    oversized_payload = {
        "value": "".join(uuid4().hex for _ in range(131_073))
    }
    with pytest.raises(psycopg.Error):
        with runtime.transaction():
            runtime.execute(
                """
                INSERT INTO datasus_raw_records
                    (source, resource_type, source_resource_id, record_key,
                     payload, fetched_at, first_ingestion_run_id,
                     last_change_run_id)
                VALUES ('synthetic', 'immunization', 'oversized-payload',
                        'row-large', %s, clock_timestamp(), %s, %s)
                """,
                (
                    Jsonb(oversized_payload),
                    run_for_payload["id"],
                    run_for_payload["id"],
                ),
            )

    monkeypatch.setenv("SERVICE_TOKEN", "database-secret-token")
    runs = IngestionRunRepository(runtime)
    run = runs.start(
        source="synthetic",
        resource_type="immunization",
        source_resource_id="resource-error",
    )
    finished = runs.finish(
        run["id"],
        status="FAILED",
        records_received=0,
        records_inserted=0,
        records_updated=0,
        error_summary=(
            "password=hunter2 token=database-secret-token patient@example.com "
            "https://example.com/x?X-Amz-Signature=abcdef"
        ),
    )
    persisted = finished["error_summary"]
    for secret in (
        "hunter2",
        "database-secret-token",
        "patient@example.com",
        "abcdef",
    ):
        assert secret not in persisted


def denied(connection, statement, values=()):
    """Like rejected(), but only a missing privilege counts (not a typo or a bad value)."""
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with connection.transaction():
            connection.execute(statement, values)


def _schema_tables(admin, schema):
    rows = admin.execute(
        """SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = %s AND c.relkind IN ('r', 'p') ORDER BY c.relname""",
        (schema,),
    ).fetchall()
    return [row["relname"] for row in rows]


def _has_table_privilege(connection, schema, table, privilege):
    qualified = '"' + schema.replace('"', '""') + '"."' + table.replace('"', '""') + '"'
    return connection.execute(
        "SELECT has_table_privilege(current_user, %s, %s) AS allowed", (qualified, privilege)
    ).fetchone()["allowed"]


def test_privilege_matrix_reader_is_read_only_and_runtime_cannot_delete(secured_database):
    admin, runtime, reader, schema = secured_database
    tables = _schema_tables(admin, schema)
    assert {"query_history", "analytical_queries", "analytical_result_versions",
            "knowledge_documents", "knowledge_chunks", "datasus_raw_records"} <= set(tables)
    for table in tables:
        for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            assert not _has_table_privilege(reader, schema, table, privilege), (table, privilege)
        for privilege in ("DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            assert not _has_table_privilege(runtime, schema, table, privilege), (table, privilege)
    for connection in (runtime, reader):
        assert connection.execute(
            "SELECT has_schema_privilege(current_user, %s, 'CREATE') AS allowed", (schema,)
        ).fetchone()["allowed"] is False


def test_specific_privilege_errors_for_history_and_result_versions(secured_database):
    _, runtime, reader, _ = secured_database
    denied(reader, "INSERT INTO query_history DEFAULT VALUES")
    denied(reader, "INSERT INTO analytical_queries DEFAULT VALUES")
    denied(runtime, "DELETE FROM analytical_queries")
    denied(runtime, "DELETE FROM query_history")
    denied(runtime, "UPDATE analytical_result_versions SET result_hash = repeat('a', 64)")
    denied(runtime, "UPDATE analytical_result_versions SET result_ciphertext = '\\x00'::bytea")
    denied(runtime, "UPDATE analytical_result_versions SET result_mac = repeat('b', 64)")
    denied(runtime, "TRUNCATE analytical_result_versions")


def test_security_definer_functions_are_not_public_and_pin_search_path(secured_database):
    admin, _, _, schema = secured_database
    functions = admin.execute(
        """SELECT p.proname, p.proconfig, p.proacl
           FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
           WHERE n.nspname = %s AND p.prosecdef""",
        (schema,),
    ).fetchall()
    assert functions, "esperava funções SECURITY DEFINER no schema"
    for function in functions:
        config = function["proconfig"] or []
        assert any(item.startswith("search_path=") for item in config), function["proname"]
        public_execute = admin.execute(
            """SELECT EXISTS (
                 SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = %s AND p.proname = %s
                   AND (p.proacl IS NULL OR EXISTS (
                         SELECT 1 FROM aclexplode(p.proacl) a
                         WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE'))
               ) AS public_execute""",
            (schema, function["proname"]),
        ).fetchone()["public_execute"]
        assert public_execute is False, function["proname"]


def _import_partition(connection, schema, tmp_path, monkeypatch, name="purge_source.csv"):
    connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
    connection.commit()
    source = tmp_path / name
    source.write_text("co_documento,co_vacina,dt_vacina,co_municipio_estabelecimento,sg_uf_estabelecimento,"
                      "tp_sexo_paciente,co_paciente,nu_cep\n"
                      "doc-a,9,2026-05-01,4314902,RS,F,PAC-1,90010000\n"
                      "doc-b,9,2026-05-02,4314902,RS,M,PAC-2,90020000\n", encoding="utf-8")
    run = ingest_csv(source, year=2026, month=5, uf="RS", resource_id="purge-resource",
                     connection=connection, batch_size=1)
    monkeypatch.setenv("POSTGRES_SCHEMA", schema)
    return source, run


def _raw_executor():
    executor = PostgresQueryExecutor()
    executor.min_cell_count = 1       # raw counts: the data path itself is under test
    return executor


def test_import_stores_only_allowlisted_columns_and_records_the_version(database, tmp_path, monkeypatch):
    connection, schema = database
    migrate(connection, schema=schema)
    _, run = _import_partition(connection, schema, tmp_path, monkeypatch)
    assert run["metadata"]["payload_allowlist_version"] == 1
    payloads = [row["payload"] for row in connection.execute("SELECT payload FROM datasus_raw_records").fetchall()]
    assert len(payloads) == 2
    for payload in payloads:
        assert "co_paciente" not in payload and "nu_cep" not in payload
        assert payload["tp_sexo_paciente"] in ("F", "M")


def test_purge_is_dry_run_by_default_and_audited(database, tmp_path, monkeypatch):
    from sus_explorer.data.persistence.purge import purge
    connection, schema = database
    migrate(connection, schema=schema)
    _import_partition(connection, schema, tmp_path, monkeypatch)
    planned = purge(connection, scope="partition", partition="ano=2026/mes=05/uf=RS",
                    reason="simulação de teste do expurgo")
    assert planned["dry_run"] is True and planned["raw_records"] == 2 and planned["immunization_records"] == 2
    assert connection.execute("SELECT count(*) AS n FROM datasus_raw_records").fetchone()["n"] == 2
    audit = connection.execute("SELECT dry_run, scope, partition, counts FROM datasus_purge_audit").fetchall()
    assert [(a["dry_run"], a["scope"], a["partition"]) for a in audit] == [(True, "partition", "ano=2026/mes=05/uf=RS")]
    assert _raw_executor().execute(QueryPlan(operation="count", year=2026, month=5, uf="RS")).data == {"doses": 2}


def test_purge_execute_removes_the_partition_and_it_becomes_unavailable_not_zero(database, tmp_path, monkeypatch):
    from sus_explorer.data.persistence.purge import purge
    connection, schema = database
    migrate(connection, schema=schema)
    source, first = _import_partition(connection, schema, tmp_path, monkeypatch)
    done = purge(connection, scope="partition", partition="ano=2026/mes=05/uf=RS",
                 reason="retirada solicitada pela fonte", execute=True)
    assert done["dry_run"] is False and done["raw_records"] == 2
    for table in ("datasus_raw_records", "immunization_records", "datasus_raw_record_revisions",
                  "datasus_raw_record_observations"):
        assert connection.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0
    # unavailable, never "0 doses"
    with pytest.raises(FileNotFoundError):
        _raw_executor().execute(QueryPlan(operation="count", year=2026, month=5, uf="RS"))
    # the immutability triggers are back on
    rejected(connection, "DELETE FROM datasus_raw_record_observations")
    rejected(connection, "DELETE FROM datasus_purge_audit")
    rejected(connection, "UPDATE datasus_purge_audit SET reason = 'tentativa de alterar a auditoria'")
    # ...and the partition can be imported again
    again = ingest_csv(source, year=2026, month=5, uf="RS", resource_id="purge-resource",
                       connection=connection, batch_size=1)
    assert again["id"] != first["id"] and again["status"] == "SUCCESS"
    assert _raw_executor().execute(QueryPlan(operation="count", year=2026, month=5, uf="RS")).data == {"doses": 2}


def test_purge_old_revisions_keeps_current_versions(database, tmp_path, monkeypatch):
    from sus_explorer.data.persistence.purge import purge
    connection, schema = database
    migrate(connection, schema=schema)
    _import_partition(connection, schema, tmp_path, monkeypatch)
    result = purge(connection, scope="old_revisions", older_than_days=30,
                   reason="retenção de revisões antigas", execute=True)
    assert result["revisions"] == 0
    assert connection.execute("SELECT count(*) AS n FROM datasus_raw_records").fetchone()["n"] == 2


def test_runtime_and_reader_cannot_purge_or_write_the_audit(secured_database, tmp_path, monkeypatch):
    from sus_explorer.data.persistence.purge import PurgeError, purge
    admin, runtime, reader, schema = secured_database
    _import_partition(admin, schema, tmp_path, monkeypatch)
    with pytest.raises(PurgeError):
        purge(runtime, scope="partition", partition="ano=2026/mes=05/uf=RS",
              reason="tentativa sem privilégio de dono", execute=True)
    runtime.rollback()
    assert admin.execute("SELECT count(*) AS n FROM datasus_raw_records").fetchone()["n"] == 2
    audit_insert = ("INSERT INTO datasus_purge_audit (scope, partition, dry_run, reason, counts) "
                    "VALUES ('partition', 'ano=2026/mes=05/uf=RS', false, 'registro falso de auditoria', '{}')")
    denied(runtime, audit_insert)
    denied(reader, audit_insert)
    assert reader.execute("SELECT count(*) AS n FROM datasus_purge_audit").fetchone()["n"] == 0


HEADER = ("co_documento,co_vacina,dt_vacina,co_municipio_estabelecimento,sg_uf_estabelecimento,"
          "tp_sexo_paciente\n")


def _csv(tmp_path, name, rows):
    path = tmp_path / name
    path.write_text(HEADER + "".join(f"{r}\n" for r in rows), encoding="utf-8")
    return path


def _import(connection, path):
    return ingest_csv(path, year=2026, month=5, uf="RS", resource_id="republished",
                      connection=connection, batch_size=1)


def _sex_counts(executor):
    result = executor.execute(QueryPlan(operation="group", group_by="sex", year=2026, month=5, uf="RS"))
    return {row["value"]: row["count"] for row in result.data["rows"]}


def _prepare(connection, schema, monkeypatch):
    migrate(connection, schema=schema)
    connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
    connection.commit()
    monkeypatch.setenv("POSTGRES_SCHEMA", schema)


V1 = ["doc-a,9,2026-05-01,4314902,RS,F", "doc-b,9,2026-05-02,4314902,RS,M", "doc-c,9,2026-05-03,4314902,RS,F"]
# doc-b changes sex, doc-c disappears, doc-d is new
V2 = ["doc-a,9,2026-05-01,4314902,RS,F", "doc-b,9,2026-05-02,4314902,RS,F", "doc-d,9,2026-05-04,4314902,RS,M"]


def test_republished_snapshot_replaces_the_previous_one_including_removed_records(database, tmp_path, monkeypatch):
    connection, schema = database
    _prepare(connection, schema, monkeypatch)
    first = _import(connection, _csv(tmp_path, "v1.csv", V1))
    executor = _raw_executor()
    assert _sex_counts(executor) == {"F": 2, "M": 1}
    second = _import(connection, _csv(tmp_path, "v2.csv", V2))
    assert second["id"] != first["id"] and second["status"] == "SUCCESS"
    assert second["metadata"]["snapshot_id"].startswith("republished/ano=2026/mes=05/uf=RS@")
    assert executor.execute(QueryPlan(operation="count", year=2026, month=5, uf="RS")).data == {"doses": 3}
    assert _sex_counts(executor) == {"F": 2, "M": 1}            # a, b(now F), d(M); c is gone
    # the removed record is retained in storage (history), just not served
    keys = {r["record_key"] for r in connection.execute("SELECT record_key FROM datasus_raw_records").fetchall()}
    assert keys == {"doc-a", "doc-b", "doc-c", "doc-d"}
    assert second["records_received"] == 3


def test_failed_reimport_rolls_back_and_the_previous_snapshot_keeps_being_served(database, tmp_path, monkeypatch):
    connection, schema = database
    _prepare(connection, schema, monkeypatch)
    _import(connection, _csv(tmp_path, "v1.csv", V1))
    _import(connection, _csv(tmp_path, "v2.csv", V2))
    executor = _raw_executor()
    before = _sex_counts(executor)
    revisions_before = connection.execute("SELECT count(*) AS n FROM datasus_raw_record_revisions").fetchone()["n"]
    bad = _csv(tmp_path, "v3.csv", ["doc-a,9,2026-05-01,4314902,RS,M", "doc-b,9,2026-05-02,4314902,RS,M",
                                    "doc-x,9,2026-06-09,4314902,RS,F"])   # last row: outside the month
    with pytest.raises(ValueError, match="fora da competência"):
        _import(connection, bad)
    # nothing from the failed snapshot is visible: counts and stored revisions are unchanged
    assert _sex_counts(executor) == before == {"F": 2, "M": 1}
    assert connection.execute("SELECT count(*) AS n FROM datasus_raw_record_revisions").fetchone()["n"] == revisions_before
    assert connection.execute("SELECT count(*) AS n FROM datasus_raw_records WHERE record_key='doc-x'").fetchone()["n"] == 0
    latest = connection.execute("SELECT status FROM datasus_ingestion_runs ORDER BY id DESC LIMIT 1").fetchone()
    assert latest["status"] == "FAILED"


def test_duplicate_record_keys_in_a_file_are_reported_and_nothing_is_committed(database, tmp_path, monkeypatch):
    connection, schema = database
    _prepare(connection, schema, monkeypatch)
    dup = _csv(tmp_path, "dup.csv", ["doc-a,9,2026-05-01,4314902,RS,F", "doc-a,9,2026-05-01,4314902,RS,F"])
    with pytest.raises(ValueError, match="duplicado"):
        _import(connection, dup)
    assert connection.execute("SELECT count(*) AS n FROM datasus_raw_records").fetchone()["n"] == 0
    with pytest.raises(FileNotFoundError):
        _raw_executor().execute(QueryPlan(operation="count", year=2026, month=5, uf="RS"))


def test_orphan_running_run_is_closed_and_the_import_proceeds(database, tmp_path, monkeypatch):
    connection, schema = database
    _prepare(connection, schema, monkeypatch)
    runs = IngestionRunRepository(connection)
    orphan = runs.start(source="opendatasus-csv", resource_type="immunization",
                        source_resource_id="republished/ano=2026/mes=05/uf=RS",
                        metadata={"partition": "ano=2026/mes=05/uf=RS", "source_sha256": "old", "source_rows": 9})
    connection.commit()
    result = _import(connection, _csv(tmp_path, "v1.csv", V1))
    assert result["status"] == "SUCCESS" and result["id"] != orphan["id"]
    closed = connection.execute("SELECT status, error_summary FROM datasus_ingestion_runs WHERE id=%s",
                                (orphan["id"],)).fetchone()
    assert closed["status"] == "FAILED" and "Orphaned" in closed["error_summary"]
    assert _raw_executor().execute(QueryPlan(operation="count", year=2026, month=5, uf="RS")).data == {"doses": 3}


def test_same_snapshot_is_idempotent_and_does_not_start_a_new_run(database, tmp_path, monkeypatch):
    connection, schema = database
    _prepare(connection, schema, monkeypatch)
    path = _csv(tmp_path, "v1.csv", V1)
    first, again = _import(connection, path), _import(connection, path)
    assert again["id"] == first["id"]
    assert connection.execute("SELECT count(*) AS n FROM datasus_ingestion_runs").fetchone()["n"] == 1
