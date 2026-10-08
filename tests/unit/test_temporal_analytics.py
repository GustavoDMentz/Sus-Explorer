from copy import deepcopy
from decimal import Decimal, localcontext
import json

import pytest

from sus_explorer.analytics import TemporalAnalytics


ORIGIN = {"source": "synthetic", "filters": {"uf": "RS"}, "missing_partitions": []}


def calculate(values, periods=None, **kwargs):
    periods = periods or [f"2026-{index + 1:02d}" for index in range(len(values))]
    return TemporalAnalytics.calculate(
        [{"period": period, "doses": value} for period, value in zip(periods, values)],
        **({
            "start_period": "2026-01", "end_period": "2026-06",
            "source_series_ref": "synthetic:monthly:v1", "source_provenance": ORIGIN,
        } | kwargs),
    )


def metric(result, order):
    return [row["metrics"][f"delta_{order}"]["value"] for row in result.data["rows"]]


@pytest.mark.parametrize("values,expected", [
    ([7] * 6, [[None, 0, 0, 0, 0, 0], [None, None, 0, 0, 0, 0], [None, None, None, 0, 0, 0]]),
    ([2 * t + 3 for t in range(6)], [[None, 2, 2, 2, 2, 2], [None, None, 0, 0, 0, 0], [None, None, None, 0, 0, 0]]),
    ([t**2 for t in range(6)], [[None, 1, 3, 5, 7, 9], [None, None, 2, 2, 2, 2], [None, None, None, 0, 0, 0]]),
    ([t**3 for t in range(6)], [[None, 1, 7, 19, 37, 61], [None, None, 6, 12, 18, 24], [None, None, None, 6, 6, 6]]),
    ([10, 8, 5, 1, 0, 0], [[None, -2, -3, -4, -1, 0], [None, None, -1, -1, 3, 1], [None, None, None, 0, 4, -2]]),
    ([0] * 6, [[None, 0, 0, 0, 0, 0], [None, None, 0, 0, 0, 0], [None, None, None, 0, 0, 0]]),
])
def test_exact_polynomial_declining_and_zero_series(values, expected):
    result = calculate(values)
    assert [metric(result, order) for order in (1, 2, 3)] == expected
    for row in result.data["rows"]:
        for item in row["metrics"].values():
            assert item["classification"] == "DERIVED"
            if item["value"] is not None:
                assert type(item["value"]) is int
                assert item["unavailable_reasons"] == []


def test_gap_never_becomes_zero_and_each_order_recovers_only_after_full_window():
    result = calculate([1, 3, 4, 5, 6], ["2026-01", "2026-03", "2026-04", "2026-05", "2026-06"])
    assert metric(result, 1) == [None, None, None, 1, 1, 1]
    assert metric(result, 2) == [None, None, None, None, 0, 0]
    assert metric(result, 3) == [None, None, None, None, None, 0]
    gap = result.data["rows"][1]
    assert gap["value"] is None
    assert gap["observation_status"] == "MISSING_MONTH"
    assert {"code": "MISSING_MONTH", "period": "2026-02"} in result.data["rows"][2]["metrics"]["delta_1"]["unavailable_reasons"]


def test_explicit_null_value_blocks_window_and_is_distinct_from_absent_month():
    result = calculate([0, None, 0, 0, 0, 0])
    assert metric(result, 1) == [None, None, None, 0, 0, 0]
    assert metric(result, 3) == [None, None, None, None, None, 0]
    assert result.data["rows"][1]["observation_status"] == "MISSING_VALUE"
    assert {"code": "MISSING_VALUE", "period": "2026-02"} in result.data["rows"][2]["metrics"]["delta_1"]["unavailable_reasons"]


def test_leading_and_trailing_missing_months_preserve_requested_interval():
    result = calculate([2, 3], ["2026-02", "2026-03"])
    assert [row["period"] for row in result.data["rows"]] == [f"2026-{m:02d}" for m in range(1, 7)]
    assert metric(result, 1) == [None, None, 1, None, None, None]


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_insufficient_series_returns_nulls_with_structured_reasons(count):
    result = calculate(list(range(count)))
    assert all(value is None for value in metric(result, 3))
    first = result.data["rows"][0]["metrics"]["delta_3"]
    assert {"code": "INSUFFICIENT_HISTORY", "period": "2025-12"} in first["unavailable_reasons"]
    assert first["value"] is None
    assert json.loads(json.dumps(result.model_dump()))["data"]["rows"][0]["metrics"]["delta_3"]["value"] is None


def test_december_january_are_adjacent():
    result = calculate([9, 7, 5, 3], ["2025-11", "2025-12", "2026-01", "2026-02"], start_period="2025-11", end_period="2026-02")
    assert metric(result, 1) == [None, -2, -2, -2]
    assert metric(result, 3) == [None, None, None, 0]


@pytest.mark.parametrize("periods", [["2026-01", "2026-01"], ["2026-02", "2026-01"]])
def test_duplicate_or_unordered_months_rejected(periods):
    with pytest.raises(ValueError, match="strictly ordered"):
        calculate([1, 2], periods)


@pytest.mark.parametrize("period", ["2026-00", "2026-13", "2026-1", "2026-01-01", "0000-01", " 2026-01", "2026-01 ", "２０２６-01", None, 202601])
def test_invalid_month_rejected(period):
    with pytest.raises(ValueError, match="period"):
        calculate([1], [period])


def test_reversed_bounds_and_rows_outside_interval_rejected():
    with pytest.raises(ValueError, match="start_period"):
        calculate([], start_period="2026-06", end_period="2026-01")
    with pytest.raises(ValueError, match="outside"):
        calculate([1], ["2025-12"])


@pytest.mark.parametrize("value", [True, 0.1, float("nan"), Decimal("NaN"), Decimal("Infinity"), "1", {}])
def test_inexact_or_invalid_values_rejected(value):
    with pytest.raises(ValueError, match="values must"):
        calculate([value])


def test_large_integers_remain_exact():
    base = 10**100
    result = calculate([base + t**3 for t in range(6)])
    assert metric(result, 3) == [None, None, None, 6, 6, 6]
    assert result.model_dump()["data"]["rows"][0]["value"] == base


def test_decimal_precision_independent_of_context_and_json_roundtrip():
    values = [Decimal("100000000000000000000.000000000000000001"),
              Decimal("100000000000000000000.000000000000000002"),
              Decimal("100000000000000000000.000000000000000003"),
              Decimal("100000000000000000000.000000000000000004")]
    with localcontext() as context:
        context.prec = 2
        result = calculate(values, end_period="2026-04")
    assert metric(result, 1) == [None] + [Decimal("0.000000000000000001")] * 3
    assert metric(result, 3)[3] == Decimal("0")
    dumped = json.loads(json.dumps(result.model_dump()))
    assert Decimal(dumped["data"]["rows"][0]["value"]) == values[0]
    assert Decimal(dumped["data"]["rows"][1]["metrics"]["delta_1"]["value"]) == Decimal("1E-18")


def test_mixed_int_decimal_and_positive_exponents_are_exact():
    result = calculate([0, Decimal("1E+2"), 200, Decimal("300.00")], end_period="2026-04")
    assert metric(result, 1) == [None, Decimal(100), Decimal(100), Decimal(100)]
    assert metric(result, 3)[3] == Decimal(0)


def test_origin_is_preserved_detached_and_deterministic():
    origin = deepcopy(ORIGIN)
    rows = [{"period": "2026-01", "doses": 3}]
    before = deepcopy(rows)
    args = dict(start_period="2026-01", end_period="2026-02", source_series_ref="query:123", source_provenance=origin)
    first = TemporalAnalytics.calculate(rows, **args)
    second = TemporalAnalytics.calculate(rows, **args)
    assert first.model_dump() == second.model_dump()
    assert rows == before and origin == ORIGIN
    assert first.provenance["source_series_ref"] == "query:123"
    assert first.provenance["source_provenance"] == ORIGIN
    origin["filters"]["uf"] = "SP"
    assert first.provenance["source_provenance"]["filters"]["uf"] == "RS"
    dumped = first.model_dump()
    dumped["provenance"]["source_provenance"]["filters"]["uf"] = "XX"
    assert first.provenance["source_provenance"]["filters"]["uf"] == "RS"


def test_formula_units_parameters_and_classification_contract():
    result = calculate([1, 4, 9, 16], unit="records", end_period="2026-04")
    provenance = result.provenance
    assert provenance["operation"] == result.operation == "temporal_finite_differences"
    assert provenance["classification"] == "DERIVED"
    assert provenance["method_version"] == "1.0.0"
    assert provenance["formulas"] == {
        "delta_1": "y(t) - y(t-1)",
        "delta_2": "y(t) - 2*y(t-1) + y(t-2)",
        "delta_3": "y(t) - 3*y(t-1) + 3*y(t-2) - y(t-3)",
    }
    assert provenance["units"] == {f"delta_{k}": f"records/month^{k}" for k in (1, 2, 3)}
    assert provenance["period"] == {"start": "2026-01", "end": "2026-04", "inclusive": True}
    assert provenance["parameters"]["alignment"] == "latest_month_backward_window"
    assert provenance["parameters"]["missing_policy"] == "null_no_gap_crossing"
    assert provenance["microdata_sent_to_llm"] is False


def test_custom_value_key():
    result = TemporalAnalytics.calculate(
        [{"period": "2026-01", "count": 0}, {"period": "2026-02", "count": -1}],
        start_period="2026-01", end_period="2026-02", source_series_ref="x",
        source_provenance={}, value_key="count", unit="records",
    )
    assert metric(result, 1) == [None, -1]


@pytest.mark.parametrize("kwargs", [{"source_series_ref": ""}, {"unit": " "}, {"value_key": "period"}, {"source_provenance": []}])
def test_invalid_metadata_rejected(kwargs):
    with pytest.raises(ValueError):
        calculate([1], **kwargs)


def test_missing_value_key_is_not_silently_treated_as_missing_observation():
    with pytest.raises(ValueError, match="each row"):
        TemporalAnalytics.calculate([{"period": "2026-01"}], start_period="2026-01", end_period="2026-01", source_series_ref="x", source_provenance={})
