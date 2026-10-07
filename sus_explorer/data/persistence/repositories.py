"""Transactional PostgreSQL operations for operational DATASUS persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import logging
from typing import Any

from psycopg.types.json import Jsonb


logger = logging.getLogger(__name__)


def _one(connection, query: str, values: tuple | list = ()) -> dict | None:
    with connection.cursor() as cursor:
        cursor.execute(query, values)
        return cursor.fetchone()


def _all(connection, query: str, values: tuple | list = ()) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(query, values)
        return cursor.fetchall()


class IngestionRunRepository:
    def __init__(self, connection):
        self.connection = connection

    def start(
        self,
        *,
        source: str,
        resource_type: str,
        source_resource_id: str,
        metadata: dict | None = None,
    ) -> dict:
        row = _one(
            self.connection,
            """
            INSERT INTO datasus_ingestion_runs
                (source, resource_type, source_resource_id, metadata)
            VALUES (%s, %s, %s, %s) RETURNING *
            """,
            (source, resource_type, source_resource_id, Jsonb(metadata or {})),
        )
        logger.info(
            "postgres_ingestion_started",
            extra={
                "event": "postgres_ingestion_started",
                "ingestion_run_id": row["id"],
                "source": source,
                "resource_type": resource_type,
                "source_resource_id": source_resource_id,
            },
        )
        return row

    def finish(
        self,
        run_id: int,
        *,
        status: str,
        records_received: int,
        records_inserted: int,
        records_updated: int,
        error_summary: str | None = None,
    ) -> dict:
        """Atomically freeze a run after serializing against record writers."""
        if status not in {"SUCCESS", "PARTIAL", "FAILED"}:
            raise ValueError("Invalid terminal ingestion status")
        with self.connection.transaction():
            run = _one(
                self.connection,
                "SELECT * FROM datasus_ingestion_runs WHERE id = %s FOR UPDATE",
                (run_id,),
            )
            if run is None or run["status"] != "RUNNING":
                raise ValueError("Ingestion run not found or already finished")
            observed = _one(
                self.connection,
                """
                SELECT count(*) AS count
                FROM datasus_raw_record_observations
                WHERE ingestion_run_id = %s
                """,
                (run_id,),
            )["count"]
            if observed > records_received:
                raise ValueError("records_received cannot be below observed records")
            result = _one(
                self.connection,
                """
                UPDATE datasus_ingestion_runs
                SET status = %s, finished_at = clock_timestamp(),
                    records_received = %s, records_inserted = %s,
                    records_updated = %s, error_summary = %s
                WHERE id = %s AND status = 'RUNNING' RETURNING *
                """,
                (
                    status,
                    records_received,
                    records_inserted,
                    records_updated,
                    error_summary,
                    run_id,
                ),
            )
        logger.info(
            "postgres_ingestion_finished",
            extra={
                "event": "postgres_ingestion_finished",
                "ingestion_run_id": run_id,
                "status": status,
                "records_received": records_received,
                "records_inserted": records_inserted,
                "records_updated": records_updated,
            },
        )
        return result


class RawRecordRepository:
    def __init__(self, connection):
        self.connection = connection

    def save(
        self,
        *,
        source: str,
        resource_type: str,
        source_resource_id: str,
        record_key: str,
        payload: dict[str, Any],
        fetched_at: datetime,
        ingestion_run_id: int,
        external_id: str | None = None,
    ) -> dict:
        """Append provenance and preserve every superseded raw revision atomically."""
        if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
            raise ValueError("fetched_at must include a timezone")
        with self.connection.transaction():
            row = _one(
                self.connection,
                """
                INSERT INTO datasus_raw_records
                    (source, resource_type, source_resource_id, record_key,
                     external_id, payload, fetched_at,
                     first_ingestion_run_id, last_change_run_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source, resource_type, source_resource_id, record_key)
                DO UPDATE SET external_id = EXCLUDED.external_id,
                              payload = EXCLUDED.payload,
                              fetched_at = EXCLUDED.fetched_at,
                              last_change_run_id = EXCLUDED.last_change_run_id
                WHERE datasus_raw_records.payload IS DISTINCT FROM EXCLUDED.payload
                   OR datasus_raw_records.external_id IS DISTINCT FROM EXCLUDED.external_id
                RETURNING *
                """,
                (
                    source,
                    resource_type,
                    source_resource_id,
                    record_key,
                    external_id,
                    Jsonb(payload),
                    fetched_at,
                    ingestion_run_id,
                    ingestion_run_id,
                ),
            )
            if row is None:
                row = _one(
                    self.connection,
                    """
                    SELECT * FROM datasus_raw_records
                    WHERE source = %s AND resource_type = %s
                      AND source_resource_id = %s AND record_key = %s
                    FOR UPDATE
                    """,
                    (source, resource_type, source_resource_id, record_key),
                )
            observation = _one(
                self.connection,
                """
                INSERT INTO datasus_raw_record_observations
                    (ingestion_run_id, raw_record_id, revision, fetched_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (ingestion_run_id, raw_record_id) DO NOTHING
                RETURNING revision
                """,
                (ingestion_run_id, row["id"], row["revision"], fetched_at),
            )
            if observation is None:
                previous = _one(
                    self.connection,
                    """
                    SELECT revision FROM datasus_raw_record_observations
                    WHERE ingestion_run_id = %s AND raw_record_id = %s
                    """,
                    (ingestion_run_id, row["id"]),
                )
                if previous["revision"] != row["revision"]:
                    raise ValueError("Source record changed within one ingestion run")
        logger.info(
            "postgres_raw_record_observed",
            extra={
                "event": "postgres_raw_record_observed",
                "ingestion_run_id": ingestion_run_id,
                "raw_record_id": row["id"],
                "revision": row["revision"],
            },
        )
        return row

    def get_by_key(
        self, source: str, resource_type: str, source_resource_id: str, record_key: str
    ) -> dict | None:
        return _one(
            self.connection,
            """
            SELECT * FROM datasus_raw_records
            WHERE source = %s AND resource_type = %s
              AND source_resource_id = %s AND record_key = %s
            """,
            (source, resource_type, source_resource_id, record_key),
        )

    def list_records(
        self,
        source: str,
        resource_type: str,
        *,
        after_id: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        if not 1 <= limit <= 1000 or after_id < 0:
            raise ValueError("Invalid pagination")
        return _all(
            self.connection,
            """
            SELECT * FROM datasus_raw_records
            WHERE source = %s AND resource_type = %s AND id > %s
            ORDER BY id LIMIT %s
            """,
            (source, resource_type, after_id, limit),
        )


class ImmunizationRepository:
    def __init__(self, connection):
        self.connection = connection

    def save(
        self,
        *,
        source_record_id: int,
        source_revision: int,
        vaccine_code: str | None = None,
        dose_code: str | None = None,
        application_date: date | None = None,
        establishment_municipality_code: str | None = None,
        establishment_uf: str | None = None,
    ) -> dict:
        row = _one(
            self.connection,
            """
            INSERT INTO immunization_records
                (source_record_id, source_revision, vaccine_code, dose_code,
                 application_date, establishment_municipality_code, establishment_uf)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_record_id) DO UPDATE
            SET source_revision = EXCLUDED.source_revision,
                vaccine_code = EXCLUDED.vaccine_code,
                dose_code = EXCLUDED.dose_code,
                application_date = EXCLUDED.application_date,
                establishment_municipality_code = EXCLUDED.establishment_municipality_code,
                establishment_uf = EXCLUDED.establishment_uf,
                updated_at = clock_timestamp()
            WHERE (immunization_records.source_revision,
                   immunization_records.vaccine_code,
                   immunization_records.dose_code,
                   immunization_records.application_date,
                   immunization_records.establishment_municipality_code,
                   immunization_records.establishment_uf)
                  IS DISTINCT FROM
                  (EXCLUDED.source_revision, EXCLUDED.vaccine_code,
                   EXCLUDED.dose_code, EXCLUDED.application_date,
                   EXCLUDED.establishment_municipality_code,
                   EXCLUDED.establishment_uf)
            RETURNING *
            """,
            (
                source_record_id,
                source_revision,
                vaccine_code,
                dose_code,
                application_date,
                establishment_municipality_code,
                establishment_uf,
            ),
        )
        if row is None:
            row = _one(
                self.connection,
                "SELECT * FROM immunization_records WHERE source_record_id = %s",
                (source_record_id,),
            )
        return row

    def list_records(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        vaccine_code: str | None = None,
        dose_code: str | None = None,
        municipality_code: str | None = None,
        uf: str | None = None,
        after_id: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        if not 1 <= limit <= 1000 or after_id < 0:
            raise ValueError("Invalid pagination")
        if start_date and end_date and start_date >= end_date:
            raise ValueError("end_date must be later than start_date")
        query = """
            SELECT i.* FROM immunization_records i
            JOIN datasus_raw_records r
              ON r.id = i.source_record_id AND r.revision = i.source_revision
            WHERE i.id > %s
        """
        values: list[Any] = [after_id]
        filters = (
            ("i.application_date >= %s", start_date),
            ("i.application_date < %s", end_date),
            ("i.vaccine_code = %s", vaccine_code),
            ("i.dose_code = %s", dose_code),
            ("i.establishment_municipality_code = %s", municipality_code),
            ("i.establishment_uf = %s", uf),
        )
        for clause, value in filters:
            if value is not None:
                query += " AND " + clause
                values.append(value)
        query += " ORDER BY i.id LIMIT %s"
        values.append(limit)
        return _all(self.connection, query, values)


@dataclass(frozen=True)
class ImmunizationProjection:
    vaccine_code: str | None = None
    dose_code: str | None = None
    application_date: date | None = None
    establishment_municipality_code: str | None = None
    establishment_uf: str | None = None


class OperationalPersistence:
    """Atomic raw + normalized write boundary used by ingestion code."""

    def __init__(self, connection):
        self.connection = connection
        self.raw = RawRecordRepository(connection)
        self.immunizations = ImmunizationRepository(connection)

    def save_immunization(
        self,
        *,
        source: str,
        resource_type: str,
        source_resource_id: str,
        record_key: str,
        payload: dict[str, Any],
        fetched_at: datetime,
        ingestion_run_id: int,
        projection: ImmunizationProjection,
        external_id: str | None = None,
    ) -> tuple[dict, dict]:
        with self.connection.transaction():
            raw = self.raw.save(
                source=source,
                resource_type=resource_type,
                source_resource_id=source_resource_id,
                record_key=record_key,
                payload=payload,
                fetched_at=fetched_at,
                ingestion_run_id=ingestion_run_id,
                external_id=external_id,
            )
            normalized = self.immunizations.save(
                source_record_id=raw["id"],
                source_revision=raw["revision"],
                vaccine_code=projection.vaccine_code,
                dose_code=projection.dose_code,
                application_date=projection.application_date,
                establishment_municipality_code=(
                    projection.establishment_municipality_code
                ),
                establishment_uf=projection.establishment_uf,
            )
        logger.info(
            "postgres_immunization_persisted",
            extra={
                "event": "postgres_immunization_persisted",
                "ingestion_run_id": ingestion_run_id,
                "raw_record_id": raw["id"],
                "revision": raw["revision"],
            },
        )
        return raw, normalized
