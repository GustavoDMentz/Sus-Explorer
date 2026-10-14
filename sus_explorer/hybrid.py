"""Conservative, opt-in access to proven complete PostgreSQL partitions."""

from __future__ import annotations

import os
import time

from .data.persistence.database import connect
from .data.persistence.ingest_r2 import RESOURCE_TYPE, SOURCE, source_snapshot
from .data.persistence.operational_events import event
from .pni import QueryResult, require_ready_plan


class HybridQueryExecutor:
    def __init__(self, r2, *, postgres_enabled: bool | None = None, connect_db=connect):
        self.r2 = r2
        self.postgres_enabled = (os.getenv("POSTGRES_COUNT_ENABLED") == "1"
                                 if postgres_enabled is None else postgres_enabled)
        self.connect_db = connect_db

    @staticmethod
    def eligible(plan) -> bool:
        # One exact R2 partition and its unfiltered row count share semantics.
        return (plan.operation == "count" and plan.year is not None and
                plan.month is not None and bool(plan.uf) and
                all(getattr(plan, name) is None for name in (
                    "day", "municipality_code", "municipality_name", "vaccine_code",
                    "vaccine_text", "age_min", "age_max", "sex", "group_by",
                    "start_year", "start_month", "end_year", "end_month",
                    "temporal_analysis")) and plan.top_n == 20)

    def execute(self, plan) -> QueryResult:
        plan = require_ready_plan(plan)
        if not self.postgres_enabled or not self.eligible(plan):
            return self.r2.execute(plan)
        try:
            result = self._postgres_count(plan)
            if result is not None:
                return result
        except Exception as exc:
            event("postgres_count_unavailable", level="WARNING", error_type=type(exc).__name__)
        return self.r2.execute(plan)

    def _postgres_count(self, plan) -> QueryResult | None:
        start = time.perf_counter()
        resource_id = self.r2.path(plan.year, plan.month, plan.uf).rstrip("/")
        with self.connect_db() as connection:
            run = connection.execute("""
                    SELECT * FROM datasus_ingestion_runs
                    WHERE source = %s AND resource_type = %s AND source_resource_id = %s
                    ORDER BY id DESC LIMIT 1
            """, (SOURCE, RESOURCE_TYPE, resource_id)).fetchone()
            if run is None or run["status"] != "SUCCESS":
                return None
            metadata = run["metadata"]
            if (metadata.get("schema_version") != 1 or
                    metadata.get("partition") !=
                    f"ano={plan.year}/mes={plan.month:02d}/uf={plan.uf}" or
                    type(metadata.get("source_rows")) is not int):
                return None
            dataset = self.r2.dataset(plan.year, plan.month, plan.uf)
            expected = source_snapshot(self.r2, dataset)
            if (expected["sha256"] != metadata.get("source_sha256") or
                    expected["fragments"] != metadata.get("fragments") or
                    dataset.count_rows() != metadata["source_rows"]):
                return None
            counts = connection.execute("""
                    SELECT
                        (SELECT count(*) FROM datasus_raw_record_observations
                         WHERE ingestion_run_id = %s) AS observed,
                        (SELECT count(*) FROM datasus_raw_records
                         WHERE source = %s AND resource_type = %s
                           AND source_resource_id = %s) AS raw_count,
                        (SELECT count(*) FROM datasus_raw_record_observations o
                         JOIN datasus_raw_records r ON r.id = o.raw_record_id
                         JOIN immunization_records i ON i.source_record_id = r.id
                         WHERE o.ingestion_run_id = %s
                           AND o.revision = r.revision
                           AND i.source_revision = r.revision) AS projected
            """, (run["id"], SOURCE, RESOURCE_TYPE, resource_id, run["id"])).fetchone()
            total = metadata["source_rows"]
            if not (run["records_received"] == counts["observed"] ==
                    counts["raw_count"] == counts["projected"] == total):
                return None
            if source_snapshot(self.r2, dataset) != expected:
                return None
            event("postgres_count_selected", ingestion_run_id=run["id"], rows=total)
            return QueryResult(
                operation="count", data={"doses": counts["projected"]},
                provenance={
                    "source": "PostgreSQL / SI-PNI R2 materialization",
                    "period": f"{plan.year}-{plan.month:02d}",
                    "partition": metadata["partition"],
                    "partitions_consulted": 1,
                    "partitions": [metadata["partition"]],
                    "parquet_fragments": expected["fragments"],
                    "columns_materialized": [],
                    "elapsed_seconds": round(time.perf_counter() - start, 3),
                    "microdata_sent_to_llm": False,
                    "executor": "postgres",
                    "ingestion_run_id": run["id"],
                    "source_sha256": expected["sha256"],
                },
            )
