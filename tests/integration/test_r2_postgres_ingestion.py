"""Real repository and routing checks against an explicitly disposable database."""

from __future__ import annotations

import os
from contextlib import contextmanager
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from psycopg import sql

from sus_explorer.data.persistence.database import connect
from sus_explorer.data.persistence.ingest_r2 import ingest_partition
from sus_explorer.data.persistence.migrate import migrate
from sus_explorer.hybrid import HybridQueryExecutor
from sus_explorer.pni import PNIRemote, QueryResult
from sus_explorer.schemas import QueryPlan


pytestmark = pytest.mark.skipif(
    os.getenv("SUS_EXPLORER_TEST_DB") != "1",
    reason="Set SUS_EXPLORER_TEST_DB=1 with a disposable PostgreSQL database",
)


@contextmanager
def borrow(connection):
    yield connection


@pytest.fixture
def database():
    schema = "ingest_test_" + uuid4().hex
    with connect() as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        connection.commit()
        try:
            connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
            connection.commit()
            migrate(connection, schema=schema)
            yield connection
        finally:
            connection.rollback()
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            connection.commit()


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "ano=2026" / "mes=05" / "uf=RS"
    path.mkdir(parents=True)

    class LocalSource:
        s3 = pa.fs.LocalFileSystem()
        r2_calls = 0

        def path(self, year, month, uf):
            return str(tmp_path / f"ano={year}" / f"mes={month:02d}" / f"uf={uf}") + "/"

        def dataset(self, year, month, uf):
            return PNIRemote.dataset(self, year, month, uf)

        def execute(self, plan):
            self.r2_calls += 1
            return QueryResult("count", {"doses": self.dataset(plan.year, plan.month, plan.uf).count_rows()},
                               {"source": "R2"})

    def write(rows):
        pq.write_table(pa.Table.from_pylist(rows), path / "part.parquet")

    rows = [
        {"co_documento": f"doc-{i}", "co_vacina": "33", "dt_vacina": "2026-05-01",
         "co_municipio_estabelecimento": "4314902", "sg_uf_estabelecimento": "RS",
         "ds_tipo_dose": "1"} for i in range(3)
    ]
    write(rows)
    return LocalSource(), rows, write


def test_initial_rerun_batch_revision_provenance_and_postgres_count(database, source):
    pni, rows, write = source
    first = ingest_partition(2026, 5, "RS", pni=pni, connection=database, batch_size=1)
    assert (first["status"], first["records_received"], first["records_inserted"]) == ("SUCCESS", 3, 3)
    assert first["metadata"]["source_rows"] == 3
    assert first["metadata"]["source_sha256"]
    second = ingest_partition(2026, 5, "RS", pni=pni, connection=database, batch_size=2)
    assert (second["status"], second["records_inserted"], second["records_updated"]) == ("SUCCESS", 0, 0)
    assert database.execute("SELECT count(*) AS n FROM datasus_raw_records").fetchone()["n"] == 3
    assert database.execute("SELECT count(*) AS n FROM datasus_raw_record_observations").fetchone()["n"] == 6
    schema = database.execute("SELECT current_schema() AS name").fetchone()["name"]
    with connect() as reopened:
        reopened.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
        persisted = reopened.execute("""
            SELECT count(*) AS n FROM immunization_records i
            JOIN datasus_raw_records r ON r.id = i.source_record_id
            WHERE i.source_revision = r.revision
              AND i.vaccine_code = r.payload->>'co_vacina'
        """).fetchone()
        assert persisted["n"] == 3
    plan = QueryPlan(operation="count", year=2026, month=5, uf="RS")
    result = HybridQueryExecutor(pni, postgres_enabled=True,
                                 connect_db=lambda: borrow(database)).execute(plan)
    assert result.data == {"doses": 3}
    assert result.provenance["executor"] == "postgres"
    assert pni.r2_calls == 0

    changed = [dict(row) for row in rows]
    changed[0]["co_vacina"] = "34"
    write(changed)
    assert HybridQueryExecutor(pni, postgres_enabled=True,
                               connect_db=lambda: borrow(database)).execute(plan).provenance["source"] == "R2"
    third = ingest_partition(2026, 5, "RS", pni=pni, connection=database, batch_size=2)
    assert third["records_updated"] == 1
    assert database.execute("SELECT count(*) AS n FROM datasus_raw_record_revisions").fetchone()["n"] == 1
    assert HybridQueryExecutor(pni, postgres_enabled=True,
                               connect_db=lambda: borrow(database)).execute(plan).provenance["executor"] == "postgres"


def test_invalid_rows_and_duplicates_never_claim_complete_coverage(database, source):
    pni, rows, write = source
    bad = [dict(row) for row in rows]
    bad[1]["dt_vacina"] = "bad"
    write(bad)
    run = ingest_partition(2026, 5, "RS", pni=pni, connection=database, batch_size=1)
    assert run["status"] == "PARTIAL"
    assert database.execute("SELECT count(*) AS n FROM datasus_raw_records").fetchone()["n"] == 2
    plan = QueryPlan(operation="count", year=2026, month=5, uf="RS")
    assert HybridQueryExecutor(pni, postgres_enabled=True,
                               connect_db=lambda: borrow(database)).execute(plan).provenance["source"] == "R2"
    duplicate = [dict(row) for row in rows]
    duplicate[1]["co_documento"] = duplicate[0]["co_documento"]
    write(duplicate)
    run = ingest_partition(2026, 5, "RS", pni=pni, connection=database, batch_size=2)
    assert run["status"] == "PARTIAL"


def test_projection_failure_rolls_back_row_and_marks_run_failed(database, source, monkeypatch):
    pni, _, _ = source
    from sus_explorer.data.persistence import ingest_r2
    original = ingest_r2.OperationalPersistence.save_immunization
    calls = 0

    def fail_second(self, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic write failure")
        return original(self, **kwargs)

    monkeypatch.setattr(ingest_r2.OperationalPersistence, "save_immunization", fail_second)
    with pytest.raises(RuntimeError, match="synthetic write failure"):
        ingest_partition(2026, 5, "RS", pni=pni, connection=database, batch_size=2)
    run = database.execute("SELECT * FROM datasus_ingestion_runs ORDER BY id DESC LIMIT 1").fetchone()
    assert run["status"] == "FAILED"
    assert database.execute("SELECT count(*) AS n FROM datasus_raw_records").fetchone()["n"] == 0


def test_interrupted_run_can_replay_without_duplicate_rows(database, source, monkeypatch):
    pni, _, _ = source
    from sus_explorer.data.persistence import ingest_r2
    original = ingest_r2.OperationalPersistence.save_immunization
    calls = 0

    def interrupt_second(self, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt()
        return original(self, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(ingest_r2.OperationalPersistence, "save_immunization", interrupt_second)
        with pytest.raises(KeyboardInterrupt):
            ingest_partition(2026, 5, "RS", pni=pni, connection=database, batch_size=1)
    run = database.execute("SELECT * FROM datasus_ingestion_runs ORDER BY id DESC LIMIT 1").fetchone()
    assert run["status"] == "RUNNING"
    resumed = ingest_partition(2026, 5, "RS", pni=pni, connection=database,
                               batch_size=2, resume_run_id=run["id"])
    assert resumed["status"] == "SUCCESS"
    assert resumed["records_received"] == 3
    assert resumed["records_inserted"] == 3
    assert database.execute("SELECT count(*) AS n FROM datasus_raw_records").fetchone()["n"] == 3
    assert database.execute("SELECT count(*) AS n FROM datasus_raw_record_observations").fetchone()["n"] == 3
