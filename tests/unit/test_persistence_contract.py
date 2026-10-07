from __future__ import annotations

import json

import psycopg
import pytest

from sus_explorer.data.persistence import database
from sus_explorer.data.persistence.migrate import MIGRATIONS
from sus_explorer.data.persistence import operational_events
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


def test_parquet_r2_modules_are_not_coupled_to_persistence():
    for path in (
        "sus_explorer/pni.py",
        "sus_explorer/build_cache.py",
        "sus_explorer/data/remote/r2.py",
        "sus_explorer/service.py",
    ):
        source = open(path, encoding="utf-8").read()
        assert "data.persistence" not in source
