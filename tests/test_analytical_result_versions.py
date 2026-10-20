"""PR #32: deterministic history invariants, without external services."""
import os
from types import SimpleNamespace

import pytest

from sus_explorer.data.persistence import result_versions as rv
from sus_explorer.schemas import QueryPlan


def _plan():
    return QueryPlan(operation="count", year=2026, month=5, uf="RS")


def _result(doses):
    return SimpleNamespace(operation="count", data={"doses": doses},
                           provenance={"partitions": ["ano=2026/mes=05/uf=RS"]})


class FakeCursor:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return self.value


class FakeTransaction:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConnection:
    def __init__(self):
        self.queries = {}
        self.versions = {}
        self.calls = []

    def transaction(self):
        return FakeTransaction()

    def execute(self, statement, params=None):
        self.calls.append((statement, params))
        if "INSERT INTO analytical_queries" in statement:
            self.queries[params[0]] = params[1]
        if "SELECT version, result_hash" in statement:
            versions = self.versions.get(params[0], [])
            return FakeCursor(versions[-1] if versions else None)
        if "INSERT INTO analytical_result_versions" in statement:
            key, version, digest = params[:3]
            self.versions.setdefault(key, []).append(
                {"version": version, "result_hash": digest, "observations": 1})
        if "UPDATE analytical_result_versions" in statement:
            _, key, version = params
            self.versions[key][-1]["observations"] += 1
        return FakeCursor(None)


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("ANALYTICAL_HISTORY_KEY", "ab" * 32)


def test_same_query_same_result_deduplicates():
    db = FakeConnection()
    a = rv.observe_result(plan=_plan(), result=_result(1179648), connection=db)
    b = rv.observe_result(plan=_plan(), result=_result(1179648), connection=db)
    assert a["version"] == b["version"] == 1
    assert not b["changed"]
    assert db.versions[a["query_key"]][0]["observations"] == 2


def test_changed_and_reverted_result_keeps_all_versions():
    db = FakeConnection()
    versions = [rv.observe_result(plan=_plan(), result=_result(n), connection=db)
                for n in (1179648, 1223529, 1179648)]
    assert [item["version"] for item in versions] == [1, 2, 3]
    assert [item["changed"] for item in versions] == [False, True, True]
    assert len(db.versions[versions[0]["query_key"]]) == 3


def test_different_period_is_different_query():
    db = FakeConnection()
    a = rv.observe_result(plan=_plan(), result=_result(10), connection=db)
    p = _plan().model_copy(update={"month": 6})
    b = rv.observe_result(plan=p, result=_result(10), connection=db)
    assert a["query_key"] != b["query_key"]


def test_rejects_missing_key_and_sensitive_payload(monkeypatch):
    monkeypatch.delenv("ANALYTICAL_HISTORY_KEY")
    with pytest.raises(RuntimeError):
        rv.observe_result(plan=_plan(), result=_result(10), connection=FakeConnection())
    monkeypatch.setenv("ANALYTICAL_HISTORY_KEY", "ab" * 32)
    bad = SimpleNamespace(operation="count", data={"cpf": "123"},
                          provenance={})
    with pytest.raises(ValueError):
        rv.observe_result(plan=_plan(), result=bad, connection=FakeConnection())


def test_ciphertext_does_not_contain_plaintext():
    db = FakeConnection()
    rv.observe_result(plan=_plan(), result=_result(1223529), connection=db)
    inserts = [params for sql, params in db.calls
               if "INSERT INTO analytical_result_versions" in sql]
    assert len(inserts) == 1
    ciphertext = inserts[0][3]
    assert b"1223529" not in ciphertext
    assert len(ciphertext) > 28
