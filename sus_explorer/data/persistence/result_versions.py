"""Compact version history for deterministic aggregate query results.

No user questions, Gemini answers, credentials, or source microdata are stored.
The result payload is limited to bounded analytical aggregates.
"""
from __future__ import annotations

import hashlib
import json

from psycopg.types.json import Jsonb

from .database import connect
from .history import safe_parameters


SEMANTICS_VERSION = 1
MAX_RESULT_BYTES = 1_000_000


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _result_payload(result) -> dict:
    if result.operation not in {"count", "group", "timeseries", "latency", "temporal"}:
        raise ValueError("Unsupported analytical operation")
    payload = {"operation": result.operation, "data": result.data}
    # Missing coverage changes the interpretation of the same numerical result.
    source = result.provenance.get("source_provenance", result.provenance)
    payload["missing_partitions"] = source.get("missing_partitions", [])
    encoded = _canonical(payload)
    if len(encoded) > MAX_RESULT_BYTES:
        raise ValueError("Analytical result exceeds storage limit")
    return payload


def observe_result(*, plan, result, connection=None) -> dict:
    """Persist first result, update identical latest, or append a changed version.

    Serializes writers per query via row locking. The database schema must have
    been migrated first. A return value never contains the stored result payload.
    """
    if plan.status != "ready" or plan.operation != result.operation:
        raise ValueError("Result does not match a ready query plan")
    # Full validated plan determines identity; do not store free-text filters.
    full_plan = plan.model_dump(exclude={"clarification_question", "missing"})
    identity = {"semantics_version": SEMANTICS_VERSION, "plan": full_plan}
    key = _digest(identity)
    safe_plan = safe_parameters(plan)
    digest = _digest(_result_payload(result))
    payload = _result_payload(result)
    own = connection is None
    if own:
        connection = connect()
    try:
        with connection.transaction():
            connection.execute(
                """INSERT INTO analytical_queries (query_key, plan, semantics_version)
                   VALUES (%s, %s, %s) ON CONFLICT (query_key) DO NOTHING""",
                (key, Jsonb(safe_plan), SEMANTICS_VERSION),
            )
            # Serialize concurrent writers on the query row.
            connection.execute(
                "SELECT query_key FROM analytical_queries WHERE query_key = %s FOR UPDATE",
                (key,),
            )
            latest = connection.execute(
                """SELECT version, result_hash FROM analytical_result_versions
                   WHERE query_key = %s ORDER BY version DESC LIMIT 1""",
                (key,),
            ).fetchone()
            if latest is not None and latest["result_hash"] == digest:
                connection.execute(
                    """UPDATE analytical_result_versions
                       SET last_seen_at = clock_timestamp(), observations = observations + 1
                       WHERE query_key = %s AND version = %s""",
                    (key, latest["version"]),
                )
                return {"query_key": key, "version": latest["version"], "changed": False}
            version = 1 if latest is None else latest["version"] + 1
            connection.execute(
                """INSERT INTO analytical_result_versions
                   (query_key, version, result_hash, result_data)
                   VALUES (%s, %s, %s, %s)""",
                (key, version, digest, Jsonb(payload)),
            )
            return {"query_key": key, "version": version, "changed": latest is not None}
    finally:
        if own:
            connection.close()
