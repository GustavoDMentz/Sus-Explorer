"""Explicit, resumable ingestion of one SI-PNI R2 Parquet partition."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timezone

import pyarrow as pa

from ...pni import PNIRemote
from .database import connect
from .operational_events import event
from .repositories import ImmunizationProjection, IngestionRunRepository, OperationalPersistence
from .validation import PAYLOAD_MAX_BYTES, validate_json_object


SOURCE = "healthbr-data-r2"
RESOURCE_TYPE = "immunization"
REQUIRED = {
    "co_documento", "co_vacina", "dt_vacina",
    "co_municipio_estabelecimento", "sg_uf_estabelecimento",
}
UFS = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())
DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}(?:$|[T ])")


def validate_partition(year: int, month: int, uf: str) -> str:
    if type(year) is not int or not 2020 <= year <= 2100:
        raise ValueError("Invalid ingestion year")
    if type(month) is not int or not 1 <= month <= 12:
        raise ValueError("Invalid ingestion month")
    if not isinstance(uf, str) or uf.upper() not in UFS:
        raise ValueError("Invalid ingestion UF")
    return uf.upper()


def source_snapshot(pni: PNIRemote, dataset) -> dict:
    """Hash object bytes, not listing timestamps, to bind coverage to exact R2 content."""
    fragments = sorted(fragment.path for fragment in dataset.get_fragments())
    if not fragments or len(fragments) != len(set(fragments)):
        raise ValueError("Partition has no unique Parquet fragments")
    digest = hashlib.sha256()
    for path in fragments:
        item = hashlib.sha256()
        with pni.s3.open_input_file(path) as stream:
            while block := stream.read(1024 * 1024):
                item.update(block)
        digest.update(json.dumps([path, item.hexdigest()], separators=(",", ":")).encode())
    return {"sha256": digest.hexdigest(), "fragments": len(fragments)}


def validate_schema(schema: pa.Schema) -> None:
    missing = REQUIRED - set(schema.names)
    if missing:
        raise ValueError("Missing required source columns: " + ", ".join(sorted(missing)))
    if len(schema.names) != len(set(schema.names)):
        raise ValueError("Duplicate source column names")
    for name in REQUIRED:
        kind = schema.field(name).type
        allowed = (pa.types.is_string(kind) or pa.types.is_large_string(kind))
        if name == "dt_vacina":
            allowed |= pa.types.is_date(kind) or pa.types.is_timestamp(kind)
        elif name != "co_documento":
            allowed |= pa.types.is_integer(kind)
        if not allowed:
            raise ValueError(f"Unsupported source type for {name}")


def _text(value, name: str, *, max_length: int = 256) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"Invalid {name}")
    result = str(value).strip()
    if not result or len(result) > max_length or "\x00" in result:
        raise ValueError(f"Invalid {name}")
    return result


def _date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and DATE_PREFIX.match(value):
        try:
            if len(value) > 10:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            return date.fromisoformat(value[:10])
        except ValueError:
            pass
    raise ValueError("Invalid dt_vacina")


def project(row: dict, uf: str) -> tuple[str, dict, ImmunizationProjection]:
    key = _text(row.get("co_documento"), "co_documento", max_length=1024)
    vaccine = _text(row.get("co_vacina"), "co_vacina")
    municipality = _text(
        row.get("co_municipio_estabelecimento"), "co_municipio_estabelecimento",
        max_length=16,
    )
    if not re.fullmatch(r"[0-9]{1,8}", vaccine):
        raise ValueError("Invalid co_vacina")
    if not re.fullmatch(r"[0-9]{6,7}", municipality):
        raise ValueError("Invalid co_municipio_estabelecimento")
    row_uf = _text(row.get("sg_uf_estabelecimento"), "sg_uf_estabelecimento", max_length=2)
    if row_uf != uf:
        raise ValueError("Source UF differs from selected partition")
    dose = next((row[name] for name in ("ds_tipo_dose", "ds_dose_vacina", "co_dose_vacina", "co_dose")
                 if name in row and row[name] is not None), None)
    dose = _text(dose, "dose") if dose is not None else None
    vaccination_date = _date(row.get("dt_vacina"))
    payload = {}
    for name, value in row.items():
        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        if value is not None and not isinstance(value, (str, int, float, bool, list, dict)):
            raise ValueError("Unsupported source value type")
        payload[name] = value
    payload = validate_json_object("payload", payload, max_bytes=PAYLOAD_MAX_BYTES)
    return key, payload, ImmunizationProjection(
        vaccine_code=vaccine, dose_code=dose, application_date=vaccination_date,
        establishment_municipality_code=municipality, establishment_uf=row_uf,
    )


def _counts(connection, run_id: int) -> dict:
    return connection.execute("""
        SELECT count(*) AS observed,
               count(*) FILTER (WHERE r.first_ingestion_run_id = %s) AS inserted,
               count(*) FILTER (WHERE r.last_change_run_id = %s
                                  AND r.first_ingestion_run_id <> %s) AS updated,
               count(*) FILTER (WHERE r.revision = o.revision
                                  AND i.source_revision = o.revision) AS projected,
               (SELECT count(*) FROM datasus_raw_records current_raw
                JOIN datasus_ingestion_runs run
                  ON (current_raw.source, current_raw.resource_type,
                      current_raw.source_resource_id) =
                     (run.source, run.resource_type, run.source_resource_id)
                WHERE run.id = %s) AS raw_count
        FROM datasus_raw_record_observations o
        JOIN datasus_raw_records r ON r.id = o.raw_record_id
        LEFT JOIN immunization_records i ON i.source_record_id = r.id
        WHERE o.ingestion_run_id = %s
    """, (run_id, run_id, run_id, run_id, run_id)).fetchone()


def ingest_partition(
    year: int, month: int, uf: str, *, pni: PNIRemote | None = None,
    connection=None, batch_size: int = 1000, resume_run_id: int | None = None,
) -> dict:
    """Process one selected partition; replay an interrupted RUNNING run from row one."""
    uf = validate_partition(year, month, uf)
    if type(batch_size) is not int or not 1 <= batch_size <= 10000:
        raise ValueError("batch_size must be between 1 and 10000")
    pni = pni or PNIRemote()
    dataset = pni.dataset(year, month, uf)
    validate_schema(dataset.schema)
    expected_rows = dataset.count_rows()
    snapshot = source_snapshot(pni, dataset)
    resource_id = pni.path(year, month, uf).rstrip("/")
    metadata = {"partition": f"ano={year}/mes={month:02d}/uf={uf}",
                "source_sha256": snapshot["sha256"],
                "fragments": snapshot["fragments"], "source_rows": expected_rows,
                "identity_column": "co_documento", "schema_version": 1}
    own_connection = connection is None
    if own_connection:
        connection = connect()
    run_id = None
    locked = False
    try:
        locked = connection.execute(
            "SELECT pg_try_advisory_lock(91627135, hashtext(%s)) AS acquired",
            (resource_id,),
        ).fetchone()["acquired"]
        if not locked:
            raise RuntimeError("Another ingestion owns this partition")
        runs = IngestionRunRepository(connection)
        if resume_run_id is not None:
            run = connection.execute(
                "SELECT * FROM datasus_ingestion_runs WHERE id = %s", (resume_run_id,)
            ).fetchone()
            if (run is None or run["status"] != "RUNNING" or
                    (run["source"], run["resource_type"], run["source_resource_id"]) !=
                    (SOURCE, RESOURCE_TYPE, resource_id) or run["metadata"] != metadata):
                raise ValueError("Run cannot be resumed for this exact source snapshot")
        else:
            run = runs.start(source=SOURCE, resource_type=RESOURCE_TYPE,
                             source_resource_id=resource_id, metadata=metadata)
        run_id = run["id"]
        connection.commit()
        event("r2_ingestion_processing", ingestion_run_id=run_id,
              expected_rows=expected_rows, batch_size=batch_size)
        persisted = OperationalPersistence(connection)
        seen = 0
        invalid = 0
        fetched_at = datetime.now(timezone.utc)
        scanner = dataset.scanner(batch_size=batch_size, use_threads=False)
        for batch in scanner.to_batches():
            for row in batch.to_pylist():
                seen += 1
                try:
                    key, payload, projection = project(row, uf)
                except (ValueError, TypeError):
                    invalid += 1
                    continue
                persisted.save_immunization(
                    source=SOURCE, resource_type=RESOURCE_TYPE,
                    source_resource_id=resource_id, record_key=key,
                    external_id=key, payload=payload, fetched_at=fetched_at,
                    ingestion_run_id=run_id, projection=projection,
                )
            connection.commit()
            event("r2_ingestion_batch", ingestion_run_id=run_id, rows_seen=seen,
                  rows_invalid=invalid)
        if source_snapshot(pni, dataset) != snapshot or seen != expected_rows:
            raise ValueError("Source snapshot changed during ingestion")
        counts = _counts(connection, run_id)
        complete = (invalid == 0 and
                    counts["observed"] == counts["projected"] ==
                    counts["raw_count"] == seen)
        status = "SUCCESS" if complete else "PARTIAL"
        summary = None if complete else (
            f"Partition incomplete: invalid_rows={invalid}, "
            f"observed={counts['observed']}, projected={counts['projected']}, "
            f"raw_count={counts['raw_count']}, source_rows={seen}"
        )
        result = runs.finish(
            run_id, status=status, records_received=seen,
            records_inserted=counts["inserted"], records_updated=counts["updated"],
            error_summary=summary,
        )
        connection.commit()
        event("r2_ingestion_completed", ingestion_run_id=run_id, status=status,
              rows_seen=seen, rows_invalid=invalid, rows_projected=counts["projected"])
        return result
    except Exception as exc:
        connection.rollback()
        if run_id is not None:
            # A failed attempt is terminal; a new run can replay the same source safely.
            try:
                counts = _counts(connection, run_id)
                runs.finish(run_id, status="FAILED", records_received=counts["observed"],
                            records_inserted=counts["inserted"],
                            records_updated=counts["updated"],
                            error_summary="Ingestion failed: " + type(exc).__name__)
                connection.commit()
            except Exception:
                connection.rollback()
        event("r2_ingestion_failed", level="ERROR", ingestion_run_id=run_id,
              error_type=type(exc).__name__)
        raise
    finally:
        if locked:
            try:
                connection.execute(
                    "SELECT pg_advisory_unlock(91627135, hashtext(%s))", (resource_id,)
                )
                connection.commit()
            except Exception:
                connection.rollback()
        if own_connection:
            connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest one explicit R2 monthly UF partition")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--uf", required=True)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--resume-run-id", type=int)
    args = parser.parse_args()
    result = ingest_partition(args.year, args.month, args.uf,
                              batch_size=args.batch_size, resume_run_id=args.resume_run_id)
    print(json.dumps({"ingestion_run_id": result["id"], "status": result["status"],
                      "records_received": result["records_received"]}))
    if result["status"] != "SUCCESS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
