from __future__ import annotations

import logging

import psycopg
import pytest

from sus_explorer.data.persistence import database
from sus_explorer.data.persistence.migrate import MIGRATIONS


def test_connection_failure_never_logs_credentials(monkeypatch, caplog):
    values = {
        "POSTGRES_HOST": "db.internal",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "sus",
        "POSTGRES_USER": "service-user",
        "POSTGRES_PASSWORD": "super-secret-value",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    def fail(**kwargs):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(database.psycopg, "connect", fail)
    with caplog.at_level(logging.INFO):
        with pytest.raises(RuntimeError, match="Could not connect"):
            database.connect()

    rendered = caplog.text
    assert "super-secret-value" not in rendered
    assert "service-user" not in rendered
    assert "db.internal" not in rendered
    assert caplog.records[-1].event == "postgres_connection_failed"


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
