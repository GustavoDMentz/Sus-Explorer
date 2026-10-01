"""Opt-in invariants against a disposable PostgreSQL database with pgvector."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from sus_explorer.data.persistence.database import connect
from sus_explorer.data.persistence.migrate import MIGRATIONS, migrate
from sus_explorer.data.persistence.repositories import (
    ImmunizationRepository,
    IngestionRunRepository,
    RawRecordRepository,
)


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
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            connection.commit()


def rejected(connection, statement, values=()):
    # Savepoint keeps the surrounding assertions usable after a DB constraint error.
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            connection.execute(statement, values)


def test_schema_and_idempotent_source_history(database):
    connection, schema = database
    assert migrate(connection) == ["001_foundation.sql"]
    assert migrate(connection) == []
    columns = {row["column_name"]: row["data_type"] for row in connection.execute("""
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_schema = %s AND table_name = 'datasus_raw_records'
    """, (schema,))}
    assert columns["payload"] == "jsonb"
    assert columns["fetched_at"] == "timestamp with time zone"
    assert connection.execute(
        "SELECT count(*) AS n FROM pg_extension WHERE extname = 'vector'"
    ).fetchone()["n"] == 1
    assert connection.execute("SELECT vector_dims('[1,2]'::vector) AS n").fetchone()["n"] == 2
    assert connection.execute("SELECT to_regclass('document_embeddings') AS t").fetchone()["t"] is None

    runs = IngestionRunRepository(connection)
    raw = RawRecordRepository(connection)
    first = runs.start(source="synthetic", resource_type="immunization",
                       source_resource_id="test-resource")
    t1 = datetime(2025, 1, 2, tzinfo=timezone.utc)
    args = dict(source="synthetic", resource_type="immunization",
                source_resource_id="test-resource", record_key="row-1")
    original = raw.save(**args, payload={"co_vacina": "33", "nested": {"ok": True}},
                        fetched_at=t1, ingestion_run_id=first["id"])
    assert original["revision"] == 1
    assert original["external_id"] is None
    again = raw.save(**args, payload=original["payload"], fetched_at=t1,
                     ingestion_run_id=first["id"])
    assert again["id"] == original["id"]
    assert again["created_at"] == original["created_at"]
    assert again["updated_at"] == original["updated_at"]
    assert len(raw.list_records("synthetic", "immunization")) == 1
    assert raw.find_by_external_id("synthetic", "immunization", "missing") == []

    second = runs.start(source="synthetic", resource_type="immunization",
                        source_resource_id="test-resource")
    t2 = t1 + timedelta(days=1)
    same = raw.save(**args, payload=original["payload"], fetched_at=t2,
                    ingestion_run_id=second["id"])
    assert same["revision"] == 1
    assert same["fetched_at"] == t1  # first fetch of the current revision
    assert same["first_ingestion_run_id"] == first["id"]
    assert connection.execute("""
        SELECT count(*) AS n FROM datasus_raw_record_observations WHERE raw_record_id = %s
    """, (same["id"],)).fetchone()["n"] == 2

    third = runs.start(source="synthetic", resource_type="immunization",
                       source_resource_id="test-resource")
    t3 = t2 + timedelta(days=1)
    changed = raw.save(**args, payload={"co_vacina": "34"}, fetched_at=t3,
                       external_id="example-1", ingestion_run_id=third["id"])
    assert changed["id"] == original["id"]
    assert changed["revision"] == 2
    assert changed["created_at"] == original["created_at"]
    assert changed["updated_at"] > original["updated_at"]
    assert changed["first_ingestion_run_id"] == first["id"]
    assert changed["last_change_run_id"] == third["id"]
    assert changed["fetched_at"] == t3
    history = connection.execute("""
        SELECT * FROM datasus_raw_record_revisions WHERE raw_record_id = %s
    """, (original["id"],)).fetchone()
    assert history["revision"] == 1
    assert history["payload"] == original["payload"]
    assert history["change_run_id"] == first["id"]
    assert len(raw.find_by_external_id("synthetic", "immunization", "example-1")) == 1
    assert raw.get_by_key(**{k: args[k] for k in args})["revision"] == 2

    with pytest.raises(ValueError, match="within one ingestion run"):
        raw.save(**args, payload={"co_vacina": "35"}, fetched_at=t3,
                 ingestion_run_id=third["id"])
    assert raw.get_by_key(**args)["revision"] == 2
    assert connection.execute("""
        SELECT count(*) AS n FROM datasus_raw_record_revisions WHERE raw_record_id = %s
    """, (original["id"],)).fetchone()["n"] == 1
    fourth = runs.start(source="synthetic", resource_type="immunization",
                        source_resource_id="test-resource")
    payload_only = raw.save(**args, payload={"co_vacina": "36"},
                            external_id="example-1", fetched_at=t3 + timedelta(days=1),
                            ingestion_run_id=fourth["id"])
    assert payload_only["revision"] == 3
    assert payload_only["created_at"] == original["created_at"]
    assert connection.execute("""
        SELECT count(*) AS n FROM datasus_raw_record_revisions WHERE raw_record_id = %s
    """, (original["id"],)).fetchone()["n"] == 2
    other_run = runs.start(source="synthetic", resource_type="immunization",
                           source_resource_id="another-resource")
    distinct_resource = raw.save(**{**args, "source_resource_id": "another-resource"},
                                 payload={}, fetched_at=t3,
                                 ingestion_run_id=other_run["id"])
    assert distinct_resource["id"] != original["id"]

    rejected(connection, """
        INSERT INTO datasus_raw_record_observations
            (ingestion_run_id, raw_record_id, revision, fetched_at)
        VALUES (%s, %s, 2, %s)
    """, (other_run["id"], original["id"], t3))

    rejected(connection, """
        UPDATE datasus_raw_records SET record_key = 'another-key' WHERE id = %s
    """, (original["id"],))
    rejected(connection, """
        INSERT INTO datasus_raw_records
            (source, resource_type, source_resource_id, record_key, payload,
             fetched_at, first_ingestion_run_id, last_change_run_id)
        VALUES ('', 'immunization', 'resource', 'key', '{}', now(), %s, %s)
    """, (first["id"], first["id"]))

    finished = runs.finish(first["id"], status="SUCCESS", records_received=1,
                           records_inserted=1, records_updated=0)
    assert finished["finished_at"] >= finished["started_at"]
    assert finished["status"] == "SUCCESS"


def test_normalized_cardinality_and_run_constraints(database):
    connection, _ = database
    migrate(connection)
    run = IngestionRunRepository(connection).start(
        source="synthetic", resource_type="immunization", source_resource_id="resource"
    )
    raw = RawRecordRepository(connection).save(
        source="synthetic", resource_type="immunization",
        source_resource_id="resource", record_key="row-1", payload={},
        fetched_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ingestion_run_id=run["id"],
    )
    normalized = ImmunizationRepository(connection)
    item = normalized.save(source_record_id=raw["id"], source_revision=1,
                           vaccine_code="33",
                           dose_code="1", application_date=date(2025, 1, 2),
                           establishment_municipality_code="4314902", establishment_uf="RS")
    same = normalized.save(source_record_id=raw["id"], source_revision=1,
                           vaccine_code="33",
                           dose_code="1", application_date=date(2025, 1, 2),
                           establishment_municipality_code="4314902", establishment_uf="RS")
    assert same["id"] == item["id"]
    assert same["created_at"] == item["created_at"]
    assert same["updated_at"] == item["updated_at"]
    changed = normalized.save(source_record_id=raw["id"], source_revision=1,
                              vaccine_code="34",
                              dose_code="1", application_date=date(2025, 1, 2),
                              establishment_municipality_code="4314902", establishment_uf="RS")
    assert changed["created_at"] == item["created_at"]
    assert changed["updated_at"] > item["updated_at"]
    assert normalized.list_records(start_date=date(2025, 1, 1),
                                   end_date=date(2025, 2, 1),
                                   vaccine_code="34", dose_code="1",
                                   municipality_code="4314902", uf="RS")[0]["id"] == item["id"]
    assert normalized.list_records(vaccine_code="other") == []

    rejected(connection,
             "INSERT INTO immunization_records (source_record_id) VALUES (%s)",
             (raw["id"],))  # UNIQUE source_record_id
    rejected(connection,
             "INSERT INTO immunization_records (source_record_id) VALUES (%s)",
             (raw["id"] + 9999,))  # FK
    rejected(connection, "DELETE FROM datasus_raw_records WHERE id = %s", (raw["id"],))
    rejected(connection, "UPDATE immunization_records SET establishment_uf = 'R' WHERE id = %s",
             (item["id"],))
    rejected(connection, "UPDATE immunization_records SET source_revision = 2 WHERE id = %s",
             (item["id"],))
    next_run = IngestionRunRepository(connection).start(
        source="synthetic", resource_type="immunization", source_resource_id="resource"
    )
    new_raw = RawRecordRepository(connection).save(
        source="synthetic", resource_type="immunization",
        source_resource_id="resource", record_key="row-1", payload={"co_vacina": "34"},
        fetched_at=datetime(2025, 1, 3, tzinfo=timezone.utc),
        ingestion_run_id=next_run["id"],
    )
    assert new_raw["revision"] == 2
    assert connection.execute("""
        SELECT source_revision <> r.revision AS stale
        FROM immunization_records i JOIN datasus_raw_records r ON r.id = i.source_record_id
        WHERE i.id = %s
    """, (item["id"],)).fetchone()["stale"] is True
    rejected(connection, "UPDATE immunization_records SET vaccine_code = '35' WHERE id = %s",
             (item["id"],))  # stale revision cannot be written again
    refreshed = normalized.save(source_record_id=raw["id"], source_revision=2,
                                vaccine_code="34", dose_code="1",
                                application_date=date(2025, 1, 2),
                                establishment_municipality_code="4314902",
                                establishment_uf="RS")
    assert refreshed["source_revision"] == 2
    rejected(connection, "UPDATE datasus_ingestion_runs SET status = 'OTHER' WHERE id = %s",
             (run["id"],))
    rejected(connection, """
        UPDATE datasus_ingestion_runs SET status = 'SUCCESS',
            finished_at = started_at - interval '1 second' WHERE id = %s
    """, (run["id"],))
    rejected(connection, """
        UPDATE datasus_ingestion_runs SET status = 'SUCCESS',
            finished_at = now(), records_received = 0, records_inserted = 1
        WHERE id = %s
    """, (run["id"],))
    rejected(connection, """
        UPDATE datasus_ingestion_runs SET status = 'SUCCESS',
            finished_at = now(), error_summary = 'unexpected'
        WHERE id = %s
    """, (run["id"],))


def test_failed_migration_rolls_back(database, tmp_path):
    connection, schema = database
    (tmp_path / "001_foundation.sql").write_bytes((MIGRATIONS / "001_foundation.sql").read_bytes())
    (tmp_path / "002_invalid.sql").write_text(
        "CREATE TABLE should_rollback (id integer); SELECT 1 / 0;", encoding="utf-8"
    )
    with pytest.raises(psycopg.Error):
        migrate(connection, tmp_path)
    assert connection.execute("""
        SELECT count(*) AS n FROM information_schema.tables WHERE table_schema = %s
    """, (schema,)).fetchone()["n"] == 0
