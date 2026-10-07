"""Opt-in invariants against a disposable PostgreSQL database with pgvector."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from sus_explorer.data.persistence.database import connect
from sus_explorer.data.persistence.migrate import MIGRATIONS, migrate
from sus_explorer.data.persistence.repositories import (
    ImmunizationProjection,
    IngestionRunRepository,
    OperationalPersistence,
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
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )
            connection.commit()


def rejected(connection, statement, values=()):
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            connection.execute(statement, values)


def test_atomic_raw_normalization_history_and_completion(database):
    connection, _ = database
    assert migrate(connection) == ["001_foundation.sql"]
    assert migrate(connection) == []

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
    connection, _ = database
    migrate(connection)
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
            projection=ImmunizationProjection(establishment_uf="INVALID"),
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
        migrate(connection, tmp_path)
    assert connection.execute(
        "SELECT count(*) AS n FROM information_schema.tables WHERE table_schema = %s",
        (schema,),
    ).fetchone()["n"] == 0

    (tmp_path / "002_invalid.sql").unlink()
    assert migrate(connection, tmp_path) == ["001_foundation.sql"]
    (tmp_path / "001_foundation.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(RuntimeError, match="changed after application"):
        migrate(connection, tmp_path)


def test_concurrent_migrations_are_serialized(database):
    connection, schema = database

    def apply_once():
        with connect() as other:
            other.execute(
                sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema))
            )
            other.commit()
            return migrate(other)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: apply_once(), range(2)))
    assert sorted(results, key=len) == [[], ["001_foundation.sql"]]
