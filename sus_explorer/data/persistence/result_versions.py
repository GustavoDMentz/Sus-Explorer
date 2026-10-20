"""Encrypted, versioned aggregate observations. No questions or LLM responses."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg.types.json import Jsonb

from .database import connect
from .history import safe_parameters, safe_provenance

SEMANTICS_VERSION = 1
MAX_RESULT_BYTES = 1_000_000
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _secret():
    raw = os.environ.get("ANALYTICAL_HISTORY_KEY", "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", raw):
        raise RuntimeError("ANALYTICAL_HISTORY_KEY must be 32 bytes encoded as 64 hex characters")
    return bytes.fromhex(raw)


def _payload(result):
    if result.operation not in {"count", "group", "timeseries", "latency", "temporal"}:
        raise ValueError("Unsupported operation")
    # Results must be aggregates. Block suspicious identifiers and unbounded output.
    data = result.data
    if not isinstance(data, dict):
        raise ValueError("Expected aggregate result dictionary")
    forbidden = re.compile(r"(?:cpf|cns|patient|paciente|nome_pessoa|email|telefone|birth_date)", re.I)
    def validate(value, depth=0):
        if depth > 12:
            raise ValueError("Result nesting too deep")
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str) or forbidden.search(key):
                    raise ValueError("Disallowed aggregate field")
                validate(item, depth + 1)
        elif isinstance(value, list):
            if len(value) > 10000:
                raise ValueError("Too many aggregate entries")
            for item in value:
                validate(item, depth + 1)
        elif value is not None and type(value) not in (str, int, float, bool):
            raise ValueError("Unexpected aggregate value")
        elif isinstance(value, str) and len(value) > 256:
            raise ValueError("Oversized aggregate label")
    validate(data)
    source = result.provenance.get("source_provenance", result.provenance)
    # Store a bounded, structured warning contract; never persist arbitrary text.
    missing = source.get("missing_partitions", [])
    if not isinstance(missing, list) or len(missing) > 36 or any(
        not isinstance(item, str) or not re.fullmatch(
            r"ano=[0-9]{4}/mes=(0[1-9]|1[0-2])/uf=[A-Z]{2}", item
        ) for item in missing
    ):
        raise ValueError("Invalid missing partitions")
    warnings = []
    if missing:
        warnings.append("MISSING_PARTITIONS")
    if getattr(result, "warnings", None) and not missing:
        warnings.append("SOURCE_WARNINGS_OMITTED")
    payload = {"operation": result.operation, "data": data,
               "missing_partitions": missing, "warnings": warnings}
    if len(_canonical(payload)) > MAX_RESULT_BYTES:
        raise ValueError("Aggregate payload too large")
    return payload


def _fingerprint(result):
    source = safe_provenance(result)
    fingerprint = source.get("source_sha256") or source.get("source_metadata_sha256")
    if fingerprint and HEX64.fullmatch(fingerprint):
        return fingerprint
    return None


def observe_result(*, plan, result, connection=None):
    """Atomic A->B->A versioning; identical latest results only increment observations."""
    if plan.status != "ready" or plan.operation != result.operation:
        raise ValueError("Result does not match ready plan")
    identity = {"semantics_version": SEMANTICS_VERSION,
                "plan": plan.model_dump(exclude={"clarification_question", "missing"})}
    key = _digest(identity)
    payload = _payload(result)
    encoded = _canonical(payload)
    digest = hashlib.sha256(encoded).hexdigest()
    secret = _secret()
    mac = hmac.new(secret, key.encode() + digest.encode() + encoded, hashlib.sha256).hexdigest()
    fingerprint = _fingerprint(result)
    own = connection is None
    if own:
        connection = connect()
    try:
        with connection.transaction():
            # Per-key serialization before first insertion, including concurrent sessions.
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (key,))
            connection.execute(
                """INSERT INTO analytical_queries (query_key, plan, semantics_version)
                   VALUES (%s, %s, %s) ON CONFLICT (query_key) DO NOTHING""",
                (key, Jsonb(safe_parameters(plan)), SEMANTICS_VERSION))
            latest = connection.execute(
                """SELECT version, result_hash FROM analytical_result_versions
                   WHERE query_key = %s ORDER BY version DESC LIMIT 1""",
                (key,)).fetchone()
            if latest and latest["result_hash"] == digest:
                connection.execute(
                    """UPDATE analytical_result_versions
                       SET last_seen_at = clock_timestamp(), observations = observations + 1
                       WHERE query_key = %s AND version = %s""",
                    (key, latest["version"]))
                return {"query_key": key, "version": latest["version"], "changed": False}
            version = latest["version"] + 1 if latest else 1
            nonce = os.urandom(12)
            ciphertext = nonce + AESGCM(secret).encrypt(nonce, encoded, key.encode())
            connection.execute(
                """INSERT INTO analytical_result_versions
                   (query_key, version, result_hash, result_ciphertext, result_mac, source_fingerprint)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (key, version, digest, ciphertext, mac, fingerprint))
            return {"query_key": key, "version": version, "changed": latest is not None}
    finally:
        if own:
            connection.close()


def get_versions(query_key, *, connection=None):
    """Read and authenticate historical snapshots. Call only in authorized context."""
    if not HEX64.fullmatch(query_key):
        raise ValueError("Invalid query key")
    secret = _secret()
    own = connection is None
    if own:
        connection = connect()
    try:
        rows = connection.execute(
            """SELECT version, result_hash, result_ciphertext, result_mac,
                      first_seen_at, last_seen_at, observations, source_fingerprint
               FROM analytical_result_versions WHERE query_key = %s ORDER BY version""",
            (query_key,)).fetchall()
        output = []
        for row in rows:
            blob = bytes(row["result_ciphertext"])
            raw = AESGCM(secret).decrypt(blob[:12], blob[12:], query_key.encode())
            digest = hashlib.sha256(raw).hexdigest()
            mac = hmac.new(secret, query_key.encode() + digest.encode() + raw, hashlib.sha256).hexdigest()
            if digest != row["result_hash"] or not hmac.compare_digest(mac, row["result_mac"]):
                raise ValueError("Historical result integrity verification failed")
            output.append({"version": row["version"], "result": json.loads(raw),
                           "first_seen_at": row["first_seen_at"],
                           "last_seen_at": row["last_seen_at"],
                           "observations": row["observations"],
                           "source_fingerprint": row["source_fingerprint"]})
        return output
    finally:
        if own:
            connection.close()
