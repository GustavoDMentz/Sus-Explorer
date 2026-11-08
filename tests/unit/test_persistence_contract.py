from __future__ import annotations

import json
from datetime import datetime, timezone

import psycopg
import pytest

from sus_explorer.data.persistence import database
from sus_explorer.data.persistence.migrate import MIGRATIONS
from sus_explorer.data.persistence import operational_events
from sus_explorer.data.persistence.repositories import (
    ImmunizationProjection,
    IngestionRunRepository,
    OperationalPersistence,
)
from sus_explorer.data.persistence.validation import (
    JSON_MAX_DEPTH,
    PAYLOAD_MAX_BYTES,
    sanitize_error_summary,
    validate_json_object,
)
from sus_explorer.operational_logging import JsonlRunLogger


def test_connection_failure_never_logs_credentials(monkeypatch, tmp_path):
    values = {
        "POSTGRES_HOST": "db.internal",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "sus",
        "POSTGRES_USER": "service-user",
        "POSTGRES_PASSWORD": "super-secret-value",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    logger = JsonlRunLogger("postgres", log_root=tmp_path, run_id="postgres-test")
    monkeypatch.setattr(operational_events, "_logger", logger)

    def fail(**kwargs):
        raise psycopg.OperationalError(
            "connection to db.internal as service-user failed; "
            "password=super-secret-value"
        )

    monkeypatch.setattr(database.psycopg, "connect", fail)
    with pytest.raises(RuntimeError, match="Could not connect"):
        database.connect()

    rendered = logger.path.read_text(encoding="utf-8")
    assert "super-secret-value" not in rendered
    assert "service-user" not in rendered
    assert "db.internal" not in rendered
    record = json.loads(rendered)
    assert record["event"] == "postgres_connection_failed"
    assert record["run_id"] == "postgres-test"
    assert record["error_type"] == "OperationalError"


def test_postgres_event_is_fail_safe_and_does_not_serialize_microdata(monkeypatch):
    class BrokenLogger:
        def event(self, *args, **kwargs):
            assert "payload" not in kwargs
            assert "patient" not in kwargs
            raise OSError("log unavailable")

    monkeypatch.setattr(operational_events, "_logger", BrokenLogger())

    saved = operational_events.event(
        "postgres_raw_record_observed",
        ingestion_run_id=10,
        raw_record_id=20,
        revision=3,
    )

    assert saved["logging_failed"] is True


def test_connection_applies_defensive_session_settings(monkeypatch):
    values = {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "sus",
        "POSTGRES_USER": "runtime",
        "POSTGRES_PASSWORD": "secret",
        "POSTGRES_SCHEMA": "sus_runtime",
        "POSTGRES_SSLMODE": "verify-full",
        "POSTGRES_CONNECT_TIMEOUT": "7",
        "POSTGRES_STATEMENT_TIMEOUT_MS": "12000",
        "POSTGRES_LOCK_TIMEOUT_MS": "900",
        "POSTGRES_IDLE_TRANSACTION_TIMEOUT_MS": "14000",
        "POSTGRES_APPLICATION_NAME": "sus-explorer-runtime",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    captured = {}

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(database.psycopg, "connect", fake_connect)
    database.connect()

    assert captured["sslmode"] == "verify-full"
    assert captured["connect_timeout"] == 7
    assert captured["application_name"] == "sus-explorer-runtime"
    assert "statement_timeout=12000" in captured["options"]
    assert "lock_timeout=900" in captured["options"]
    assert "idle_in_transaction_session_timeout=14000" in captured["options"]
    assert "search_path=sus_runtime,pg_catalog" in captured["options"]


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("POSTGRES_SCHEMA", "public,evil"),
        ("POSTGRES_SSLMODE", "trust-me"),
        ("POSTGRES_STATEMENT_TIMEOUT_MS", "0"),
        ("POSTGRES_LOCK_TIMEOUT_MS", "not-a-number"),
    ),
)
def test_connection_rejects_unsafe_configuration(monkeypatch, name, value):
    for key, configured in {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "sus",
        "POSTGRES_USER": "runtime",
        "POSTGRES_PASSWORD": "secret",
    }.items():
        monkeypatch.setenv(key, configured)
    monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match="PostgreSQL setting"):
        database.connect()


def test_json_limits_reject_large_and_deep_payloads():
    with pytest.raises(ValueError, match="allowed size"):
        validate_json_object(
            "payload", {"value": "x" * PAYLOAD_MAX_BYTES}, max_bytes=PAYLOAD_MAX_BYTES
        )

    nested = {}
    cursor = nested
    for _ in range(JSON_MAX_DEPTH + 1):
        cursor["child"] = {}
        cursor = cursor["child"]
    with pytest.raises(ValueError, match="complexity"):
        validate_json_object("payload", nested, max_bytes=PAYLOAD_MAX_BYTES)


def test_error_summary_is_sanitized_and_bounded(monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN", "known-token-value")
    summary = sanitize_error_summary(
        "password=hunter2 token=known-token-value user@example.com "
        "123.456.789-00 https://user:pass@example.com/object?X-Amz-Signature=abc "
        + "x" * 3000
    )

    assert len(summary) == 2048
    for secret in (
        "hunter2",
        "known-token-value",
        "user@example.com",
        "123.456.789-00",
        "user:pass",
        "abc",
    ):
        assert secret not in summary


def test_repository_rejects_identifiers_before_database_access():
    class NoDatabase:
        def transaction(self):
            raise AssertionError("database must not be reached")

    runs = IngestionRunRepository(NoDatabase())
    with pytest.raises(ValueError, match="allowed size"):
        runs.start(
            source="x" * 129,
            resource_type="immunization",
            source_resource_id="resource",
        )

    persistence = OperationalPersistence(NoDatabase())
    with pytest.raises(ValueError, match="allowed size"):
        persistence.save_immunization(
            source="synthetic",
            resource_type="immunization",
            source_resource_id="resource",
            record_key="x" * 1025,
            payload={"value": 1},
            fetched_at=datetime.now(timezone.utc),
            ingestion_run_id=1,
            projection=ImmunizationProjection(),
        )


def test_migration_declares_database_enforced_invariants():
    sql = (MIGRATIONS / "001_foundation.sql").read_text(encoding="utf-8")
    required_fragments = (
        "raw_revisions_immutable",
        "raw_observations_immutable",
        "raw_change_removes_stale_immunization",
        "ingestion_run_protected",
        "validate_raw_observation",
        "CREATE EXTENSION IF NOT EXISTS vector",
    )
    for fragment in required_fragments:
        assert fragment in sql

    hardening = (MIGRATIONS / "002_security_hardening.sql").read_text(
        encoding="utf-8"
    )
    for fragment in (
        "sus_explorer_migrator",
        "sus_explorer_runtime",
        "sus_explorer_reader",
        "REVOKE ALL ON ALL TABLES",
        "SECURITY DEFINER",
        "raw_payload_size",
    ):
        assert fragment in hardening


def test_parquet_r2_modules_are_not_coupled_to_persistence():
    for path in (
        "sus_explorer/pni.py",
        "sus_explorer/build_cache.py",
        "sus_explorer/data/remote/r2.py",
        "sus_explorer/service.py",
    ):
        source = open(path, encoding="utf-8").read()
        assert "data.persistence" not in source
