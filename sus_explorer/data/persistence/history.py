"""Optional query metadata history; never persists questions or result payloads."""

from __future__ import annotations

import re
from uuid import UUID

from psycopg.types.json import Jsonb

from .database import connect


PARAMETER_FIELDS = (
    "year", "month", "start_year", "start_month", "end_year", "end_month",
    "uf", "municipality_code", "vaccine_code", "age_min", "age_max",
    "sex", "top_n",
)
PARTITION = re.compile(r"^ano=\d{4}/mes=(0[1-9]|1[0-2])/uf=[A-Z]{2}$")


def safe_parameters(plan) -> dict:
    """Keep typed codes and dates; omit free text that might contain personal data."""
    values = {name: getattr(plan, name) for name in PARAMETER_FIELDS
              if getattr(plan, name, None) is not None}
    for name, pattern in {
        "uf": r"[A-Z]{2}",
        "municipality_code": r"[0-9]{6,7}",
        "vaccine_code": r"[0-9]{1,8}",
    }.items():
        if name in values and not re.fullmatch(pattern, str(values[name])):
            values.pop(name)
    if getattr(plan, "group_by", None) in {
        "vaccine", "municipality", "sex", "age", "dose", "facility", "system_origin", "race"
    }:
        values["group_by"] = plan.group_by
    temporal = getattr(plan, "temporal_analysis", None)
    if temporal is not None:
        values["temporal_analysis"] = temporal.model_dump()
    return values


def safe_provenance(result) -> dict:
    source = result.provenance.get("source_provenance", result.provenance)
    output = {}
    for name in ("period", "source_sha256", "source_metadata_sha256"):
        value = source.get(name)
        if isinstance(value, str) and len(value) <= 128:
            output[name] = value
    for name in ("partitions", "missing_partitions"):
        value = source.get(name)
        if isinstance(value, list) and len(value) <= 36 and all(
            isinstance(item, str) and PARTITION.fullmatch(item) for item in value
        ):
            output[name] = value
    run_id = source.get("ingestion_run_id")
    if type(run_id) is int and run_id > 0:
        output["ingestion_run_id"] = run_id
    return output


def record_query(*, query_id: UUID, plan, executor: str, status: str,
                 duration_ms: int, provenance: dict | None = None,
                 connection=None) -> None:
    if executor not in {"r2", "postgres", "unknown"} or status not in {"SUCCESS", "FAILED"}:
        raise ValueError("Invalid query history status or executor")
    if type(duration_ms) is not int or duration_ms < 0:
        raise ValueError("Invalid query history duration")
    if not isinstance(query_id, UUID) or plan.operation is None:
        raise ValueError("Invalid query history identity or operation")
    own_connection = connection is None
    if own_connection:
        connection = connect()
    try:
        with connection.transaction():
            connection.execute(
                """INSERT INTO query_history
                   (id, operation, parameters, executor, status, duration_ms, provenance)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (query_id, plan.operation, Jsonb(safe_parameters(plan)), executor,
                 status, duration_ms, Jsonb(provenance or {})),
            )
    finally:
        if own_connection:
            connection.close()


def recent_queries(*, limit: int = 20, connection=None) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid query history limit")
    own_connection = connection is None
    if own_connection:
        connection = connect()
    try:
        return connection.execute(
            """SELECT id, executed_at, operation, parameters, executor, status,
                      duration_ms, provenance, result_ref
               FROM query_history ORDER BY executed_at DESC, id DESC LIMIT %s""",
            (limit,),
        ).fetchall()
    finally:
        if own_connection:
            connection.close()
