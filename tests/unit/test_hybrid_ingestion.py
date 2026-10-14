from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from sus_explorer.data.persistence.ingest_r2 import (
    project, source_snapshot, validate_partition, validate_schema,
)
from sus_explorer.hybrid import HybridQueryExecutor
from sus_explorer.pni import PNIRemote, QueryResult
from sus_explorer.schemas import QueryPlan
from sus_explorer.service import SUSExplorer


def make_source(tmp_path: Path):
    path = tmp_path / "ano=2026" / "mes=05" / "uf=RS"
    path.mkdir(parents=True)
    pq.write_table(pa.table({
        "co_documento": ["doc-1", "doc-2"],
        "co_vacina": ["33", "33"],
        "dt_vacina": ["2026-05-01", "2026-05-02"],
        "co_municipio_estabelecimento": ["4314902", "4314902"],
        "sg_uf_estabelecimento": ["RS", "RS"],
    }), path / "part.parquet")

    class Source:
        s3 = pa.fs.LocalFileSystem()

        def path(self, year, month, uf):
            return str(tmp_path / f"ano={year}" / f"mes={month:02d}" / f"uf={uf}") + "/"

        def dataset(self, year, month, uf):
            return PNIRemote.dataset(self, year, month, uf)

        def execute(self, plan):
            self.r2_calls += 1
            return QueryResult(
                "count",
                {"doses": self.dataset(plan.year, plan.month, plan.uf).count_rows()},
                {"source": "R2"},
            )

        r2_calls = 0

    return Source(), path


def test_partition_and_source_schema_are_explicit(tmp_path):
    source, path = make_source(tmp_path)
    dataset = source.dataset(2026, 5, "RS")
    assert validate_partition(2026, 5, "rs") == "RS"
    validate_schema(dataset.schema)
    before = source_snapshot(source, dataset)
    assert before["fragments"] == 1
    (path / "part.parquet").write_bytes((path / "part.parquet").read_bytes() + b"changed")
    assert source_snapshot(source, dataset)["sha256"] != before["sha256"]
    with pytest.raises(ValueError, match="month"):
        validate_partition(2026, 13, "RS")
    with pytest.raises(ValueError, match="co_documento"):
        validate_schema(pa.schema([("co_vacina", pa.string())]))
    with pytest.raises(ValueError, match="co_documento"):
        validate_schema(pa.schema([(name, pa.int64() if name == "co_documento" else pa.string())
                                   for name in sorted({"co_documento", "co_vacina", "dt_vacina",
                                                       "co_municipio_estabelecimento", "sg_uf_estabelecimento"})]))


def test_projection_rejects_missing_identity_wrong_uf_and_bad_date():
    row = {"co_documento": "doc-1", "co_vacina": "33", "dt_vacina": "2026-05-01",
           "co_municipio_estabelecimento": "4314902", "sg_uf_estabelecimento": "RS"}
    key, payload, projection = project(row, "RS")
    assert key == "doc-1" and payload == row
    assert projection.application_date == date(2026, 5, 1)
    for change in ({"co_documento": None}, {"sg_uf_estabelecimento": "SP"},
                   {"dt_vacina": "2026-02-31"}, {"other": float("nan")}):
        with pytest.raises(ValueError):
            project(row | change, "RS")


def test_hybrid_disabled_and_unsupported_filters_never_open_postgres(tmp_path):
    source, _ = make_source(tmp_path)
    plan = QueryPlan(operation="count", year=2026, month=5, uf="RS")
    def forbidden():
        pytest.fail("PostgreSQL must not be accessed")
    assert HybridQueryExecutor(source, postgres_enabled=False, connect_db=forbidden).execute(plan).data == {"doses": 2}
    filtered = plan.model_copy(update={"vaccine_code": "33"})
    assert HybridQueryExecutor(source, postgres_enabled=True, connect_db=forbidden).execute(filtered).provenance["source"] == "R2"
    assert source.r2_calls == 2


def test_hybrid_requires_complete_current_source_and_falls_back_on_db_outage(tmp_path):
    source, _ = make_source(tmp_path)
    plan = QueryPlan(operation="count", year=2026, month=5, uf="RS")
    snapshot = source_snapshot(source, source.dataset(2026, 5, "RS"))
    run = {"id": 7, "status": "SUCCESS", "records_received": 2,
           "metadata": {"schema_version": 1, "partition": "ano=2026/mes=05/uf=RS",
                        "source_rows": 2, "source_sha256": snapshot["sha256"],
                        "fragments": 1}}

    class Cursor:
        def __init__(self, row):
            self.row = row
        def fetchone(self):
            return self.row

    class Connection:
        def __init__(self, counts):
            self.counts = counts
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def execute(self, statement, values):
            return Cursor(self.counts if "AS observed" in statement else run)

    executor = HybridQueryExecutor(source, postgres_enabled=True,
                                  connect_db=lambda: Connection({"observed": 2,
                                                                   "raw_count": 2,
                                                                   "projected": 2}))
    result = executor.execute(plan)
    assert result.data == {"doses": 2}
    assert result.provenance["executor"] == "postgres"
    assert result.provenance["ingestion_run_id"] == 7
    assert source.r2_calls == 0
    incomplete = HybridQueryExecutor(source, postgres_enabled=True,
                                     connect_db=lambda: Connection({"observed": 1,
                                                                      "raw_count": 2,
                                                                      "projected": 1}))
    assert incomplete.execute(plan).provenance["source"] == "R2"
    run["metadata"]["source_sha256"] = "stale"
    assert executor.execute(plan).provenance["source"] == "R2"
    outage = HybridQueryExecutor(source, postgres_enabled=True,
                                 connect_db=lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    assert outage.execute(plan).provenance["source"] == "R2"


def test_existing_empty_partition_can_return_zero_but_missing_partition_cannot(tmp_path):
    source, path = make_source(tmp_path)
    table = pq.read_table(path / "part.parquet")
    pq.write_table(table.slice(0, 0), path / "part.parquet")
    plan = QueryPlan(operation="count", year=2026, month=5, uf="RS")
    snapshot = source_snapshot(source, source.dataset(2026, 5, "RS"))
    run = {"id": 8, "status": "SUCCESS", "records_received": 0,
           "metadata": {"schema_version": 1, "partition": "ano=2026/mes=05/uf=RS",
                        "source_rows": 0, "source_sha256": snapshot["sha256"],
                        "fragments": 1}}

    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def execute(self, statement, values):
            value = ({"observed": 0, "raw_count": 0, "projected": 0}
                     if "AS observed" in statement else run)
            return SimpleCursor(value)

    class SimpleCursor:
        def __init__(self, value):
            self.value = value
        def fetchone(self):
            return self.value

    result = HybridQueryExecutor(source, postgres_enabled=True,
                                 connect_db=Connection).execute(plan)
    assert result.data == {"doses": 0}
    assert result.provenance["executor"] == "postgres"
    (path / "part.parquet").unlink()
    with pytest.raises((FileNotFoundError, OSError, ValueError)):
        HybridQueryExecutor(source, postgres_enabled=True,
                            connect_db=Connection).execute(plan)


def test_service_routes_valid_plan_through_hybrid_without_changing_llm_contract():
    plan = QueryPlan(operation="count", year=2026, month=5, uf="RS")
    result = QueryResult("count", {"doses": 3}, {"source": "PostgreSQL"})
    service = SUSExplorer.__new__(SUSExplorer)
    service.llm = SimpleNamespace(plan=lambda _: plan,
                                  answer=lambda question, planned, aggregated: "3 doses")
    service.pni = SimpleNamespace(execute=lambda _: pytest.fail("Direct R2 bypass"))
    service.executor = SimpleNamespace(execute=lambda _: result)
    response = service.ask("Quantas doses no RS em maio de 2026?")
    assert response["result"]["data"] == {"doses": 3}
    assert response["answer"] == "3 doses"
