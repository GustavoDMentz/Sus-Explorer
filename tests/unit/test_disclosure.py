import pytest

from sus_explorer import disclosure
from sus_explorer.postgres_executor import PostgresQueryExecutor
from sus_explorer.schemas import QueryPlan

K = 5


def test_threshold_defaults_to_five_and_cannot_be_lowered(monkeypatch):
    monkeypatch.delenv("SUS_MIN_CELL_COUNT", raising=False)
    assert disclosure.configured_min_cell_count() == 5
    monkeypatch.setenv("SUS_MIN_CELL_COUNT", "10")
    assert disclosure.configured_min_cell_count() == 10
    for bad in ("4", "1", "0", "abc"):
        monkeypatch.setenv("SUS_MIN_CELL_COUNT", bad)
        with pytest.raises(ValueError):
            disclosure.configured_min_cell_count()
    with pytest.raises(ValueError):
        disclosure.configured_min_cell_count(3)


@pytest.mark.parametrize("n, small", [(0, False), (1, True), (4, True), (5, False), (6, False)])
def test_only_positive_counts_below_threshold_are_small(n, small):
    assert disclosure.is_small(n, K) is small
    assert disclosure.is_small(None, K) is False
    assert disclosure.is_small(True, K) is False


def test_count_is_suppressed_below_threshold():
    data = {"doses": 3}
    assert disclosure.apply("count", data, K) == 1
    assert data["doses"] is None and data["suppressed"] and data["count_display"] == "menos de 5"
    ok = {"doses": 5}
    assert disclosure.apply("count", ok, K) == 0 and ok == {"doses": 5}


def test_timeseries_suppresses_small_months_and_keeps_zero():
    data = {"rows": [{"period": "2026-01", "doses": 3}, {"period": "2026-02", "doses": 0},
                     {"period": "2026-03", "doses": 9}]}
    assert disclosure.apply("timeseries", data, K) == 1
    assert [r["doses"] for r in data["rows"]] == [None, 0, 9]


def test_group_hides_total_when_a_single_suppressed_cell_could_be_recovered():
    data = {"rows": [{"value": "F", "count": 50}, {"value": "M", "count": 3}], "total_after_filters": 53}
    disclosure.apply("group", data, K)
    assert data["rows"][1]["count"] is None and data["rows"][1]["count_display"] == "menos de 5"
    assert data["total_after_filters"] is None and data["total_suppressed"] is True


def test_group_keeps_total_when_nothing_is_withheld():
    data = {"rows": [{"value": "F", "count": 50}, {"value": "M", "count": 40}], "total_after_filters": 90}
    assert disclosure.apply("group", data, K) == 0
    assert data["total_after_filters"] == 90


def test_group_hides_total_when_truncation_leaves_a_small_remainder():
    # top_n cut off one cell of 2 people: total - shown == 2 would reveal it.
    data = {"rows": [{"value": "a", "count": 20}, {"value": "b", "count": 10}], "total_after_filters": 32}
    disclosure.apply("group", data, K)
    assert data["total_after_filters"] is None


def test_group_keeps_total_when_remainder_is_large_enough():
    data = {"rows": [{"value": "a", "count": 20}], "total_after_filters": 28}   # remainder 8 >= 5
    disclosure.apply("group", data, K)
    assert data["total_after_filters"] == 28


def test_latency_percentiles_are_suppressed_for_few_records():
    data = {"n_valid": 3, "median_days": 1.0, "p90_days": 2.0, "p95_days": 3.0}
    assert disclosure.apply("latency", data, K) == 1
    assert data["median_days"] is None and data["p90_days"] is None and data["suppressed"]
    big = {"n_valid": 50, "median_days": 1.0, "p90_days": 2.0, "p95_days": 3.0}
    assert disclosure.apply("latency", big, K) == 0 and big["median_days"] == 1.0


@pytest.mark.parametrize("age_min, age_max, expected", [
    (87, 87, (85, 89, True)),
    (0, 4, (0, 4, False)),
    (18, 64, (15, 64, True)),
    (None, 59, (None, 59, False)),
    (60, None, (60, None, False)),
    (196, 200, (195, 200, True)),
])
def test_age_filters_snap_outward_to_five_year_bands(age_min, age_max, expected):
    assert disclosure.snap_age_range(age_min, age_max) == expected


class FakeDb:
    """Minimal connection: one ready partition and a configurable count."""

    def __init__(self, count):
        self.count = count
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, values=()):
        self.queries.append((query, values))
        return self

    def fetchone(self):
        return {"n": self.count}

    def fetchall(self):
        return []


def executor_with(count):
    executor = PostgresQueryExecutor(connect_db=lambda: FakeDb(count))
    executor._ready = lambda db, plan: ([{"id": 1, "metadata": {"partition": "ano=2026/mes=05/uf=RS"},
                                          "source": "s"}], [])
    return executor


def test_executor_suppresses_small_counts_and_warns():
    result = executor_with(3).execute(QueryPlan(operation="count", year=2026, month=5, uf="RS"))
    assert result.data["doses"] is None
    assert any("suprimidos" in w for w in result.warnings)
    assert result.provenance["disclosure_control"] == {"min_cell_count": 5, "suppressed_cells": 1,
                                                       "age_band_years": 5}


def test_executor_keeps_large_counts_and_the_age_band_is_widened_with_a_warning():
    plan = QueryPlan(operation="count", year=2026, month=5, uf="RS", age_min=87, age_max=87)
    result = executor_with(50).execute(plan)
    assert result.data["doses"] == 50
    assert any("85–89" in w for w in result.warnings)
    assert result.provenance["disclosure_control"]["suppressed_cells"] == 0


def test_temporal_series_treats_a_suppressed_month_as_unavailable_and_keeps_the_notice():
    from types import SimpleNamespace
    from sus_explorer.analytics.temporal_query import execute_temporal

    def source(plan):
        rows = [{"period": "2026-01", "doses": 40}, {"period": "2026-02", "doses": None},
                {"period": "2026-03", "doses": 60}]
        return SimpleNamespace(operation="timeseries", data={"rows": rows}, warnings=[
            disclosure.SUPPRESSION_WARNING.format(k=5)], provenance={
                "source": "SI-PNI / PostgreSQL", "uf_partition": "RS", "microdata_sent_to_llm": False})

    plan = QueryPlan(operation="temporal", uf="RS", start_year=2026, start_month=1,
                     end_year=2026, end_month=3, temporal_analysis={"order": 1})
    result = execute_temporal(plan, source)
    statuses = {row["period"]: row["observation_status"] for row in result.data["rows"]}
    assert statuses["2026-02"] != "OBSERVED"                      # suppressed, not a number
    assert statuses["2026-01"] == "OBSERVED" and statuses["2026-03"] == "OBSERVED"
    march = next(r for r in result.data["rows"] if r["period"] == "2026-03")
    assert march["metrics"]["delta_1"]["value"] is None            # no delta across the gap
    assert any("suprimidos" in w for w in result.warnings)
