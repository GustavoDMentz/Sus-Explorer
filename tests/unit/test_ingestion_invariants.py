from contextlib import contextmanager

import pytest

from sus_explorer.data.persistence import database
from sus_explorer.data.persistence.repositories import IngestionRunRepository


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, values=()):
        self.connection.queries.append(query)
        text = " ".join(query.split())
        if "FROM datasus_ingestion_runs WHERE id" in text and text.startswith("SELECT"):
            self.row = {"status": "RUNNING", "id": 1}
        elif "count(*) AS count" in text:
            self.row = {"count": self.connection.observed}
        elif text.startswith("UPDATE datasus_ingestion_runs"):
            self.row = {"id": 1, "status": values[0], "records_received": values[1]}
        else:
            self.row = None

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, observed):
        self.observed = observed
        self.queries = []

    @contextmanager
    def transaction(self):
        yield

    def cursor(self):
        return FakeCursor(self)

    def execute(self, query, values=()):
        self.queries.append((query, values))


def finish(observed, received, status="SUCCESS"):
    runs = IngestionRunRepository(FakeConnection(observed))
    return runs.finish(1, status=status, records_received=received,
                       records_inserted=received, records_updated=0)


def test_success_requires_received_equal_to_observed():
    assert finish(3, 3)["status"] == "SUCCESS"
    with pytest.raises(ValueError, match="SUCCESS requires"):
        finish(3, 5)            # contagem inflada: parcial não pode parecer completa


def test_observed_above_received_is_still_rejected():
    with pytest.raises(ValueError, match="cannot be below"):
        finish(5, 3)


@pytest.mark.parametrize("status", ["PARTIAL", "FAILED"])
def test_partial_and_failed_runs_may_have_a_gap(status):
    assert finish(3, 5, status=status)["status"] == status


def test_long_statement_timeout_is_transaction_local(monkeypatch):
    connection = FakeConnection(0)
    monkeypatch.delenv("POSTGRES_INGEST_STATEMENT_TIMEOUT_MS", raising=False)
    database.allow_long_ingestion_statement(connection)
    query, values = connection.queries[-1]
    assert "set_config('statement_timeout'" in query and "true" in query   # is_local = true
    assert values == ("300000",)


@pytest.mark.parametrize("value", ["999", "3600001", "abc"])
def test_ingest_timeout_setting_is_bounded(monkeypatch, value):
    monkeypatch.setenv("POSTGRES_INGEST_STATEMENT_TIMEOUT_MS", value)
    with pytest.raises(RuntimeError):
        database.allow_long_ingestion_statement(FakeConnection(0))
