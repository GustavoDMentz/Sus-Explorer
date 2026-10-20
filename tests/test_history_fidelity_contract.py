"""Contract tests for historical scientific fidelity and immutable origin."""
from types import SimpleNamespace

from sus_explorer.data.persistence import result_versions as rv
from sus_explorer.schemas import QueryPlan


def test_missing_partition_warning_is_retained_without_arbitrary_text():
    result = SimpleNamespace(
        operation="timeseries",
        data={"rows": [{"period": "2026-01", "doses": 10}]},
        provenance={"missing_partitions": ["ano=2026/mes=02/uf=RS"]},
        warnings=["Algumas partições mensais não estavam disponíveis e foram ignoradas: ano=2026/mes=02/uf=RS"],
    )
    payload = rv._payload(result)
    assert payload["missing_partitions"] == ["ano=2026/mes=02/uf=RS"]
    assert payload["warnings"], "Historical warning must not silently disappear"


def test_duplicate_observation_must_not_rewrite_original_fingerprint(monkeypatch):
    monkeypatch.setenv("ANALYTICAL_HISTORY_KEY", "ab" * 32)
    from test_analytical_result_versions import FakeConnection
    db = FakeConnection()
    plan = QueryPlan(operation="count", year=2026, month=5, uf="RS")
    def result(fingerprint):
        return SimpleNamespace(operation="count", data={"doses": 10},
            provenance={"source_metadata_sha256": fingerprint})
    rv.observe_result(plan=plan, result=result("a" * 64), connection=db)
    rv.observe_result(plan=plan, result=result("b" * 64), connection=db)
    updates = [sql for sql, _ in db.calls if "UPDATE analytical_result_versions" in sql]
    assert updates and "source_fingerprint" not in updates[0]
