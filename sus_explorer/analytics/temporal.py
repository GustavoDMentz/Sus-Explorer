"""Exact backward monthly finite differences; no data access or LLM calls."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from math import comb
import json
import re
from typing import Any, Mapping, Sequence


METHOD_VERSION = "1.0.0"
FORMULAS = {
    1: "y(t) - y(t-1)",
    2: "y(t) - 2*y(t-1) + y(t-2)",
    3: "y(t) - 3*y(t-1) + 3*y(t-2) - y(t-3)",
}


def _month(period: str) -> int:
    if not isinstance(period, str) or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", period):
        raise ValueError("period must be a valid YYYY-MM month")
    year, month = map(int, period.split("-"))
    if year == 0:
        raise ValueError("period year must be between 0001 and 9999")
    return (year - 1) * 12 + month - 1


def _period(month: int) -> str:
    year, offset = divmod(month, 12)
    return f"{year + 1:04d}-{offset + 1:02d}"


def _difference(values: list[int | Decimal], order: int) -> int | Decimal:
    coefficients = [(-1) ** k * comb(order, k) for k in range(order + 1)]
    if all(type(value) is int for value in values):
        return sum(coefficient * value for coefficient, value in zip(coefficients, values))
    # Integer scaling is exact even when the caller's Decimal context is tiny.
    decimals = [value if isinstance(value, Decimal) else Decimal(value) for value in values]
    exponent = min(value.as_tuple().exponent for value in decimals)
    total = 0
    for coefficient, value in zip(coefficients, decimals):
        parts = value.as_tuple()
        digits = int("".join(map(str, parts.digits)))
        scaled = (-1 if parts.sign else 1) * digits * 10 ** (parts.exponent - exponent)
        total += coefficient * scaled
    return Decimal((int(total < 0), tuple(map(int, str(abs(total)))), exponent))


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return deepcopy(value)


@dataclass
class TemporalAnalyticsResult:
    """QueryResult-shaped output; Decimal values encode as exact JSON strings."""

    operation: str
    data: dict
    provenance: dict
    warnings: list[str]

    def model_dump(self) -> dict:
        return _json_value({
            "operation": self.operation,
            "data": self.data,
            "provenance": self.provenance,
            "warnings": self.warnings,
        })


class TemporalAnalytics:
    """Calculate orders 1–3, aligned to the latest month of each window.

    Input rows must already be aggregated and strictly ordered. Values accept
    Python int, finite Decimal or None; floats and bools are deliberately rejected.
    Explicit inclusive bounds preserve absent leading/trailing months as well.
    """

    @staticmethod
    def calculate(
        rows: Sequence[Mapping[str, Any]],
        *,
        start_period: str,
        end_period: str,
        source_series_ref: str,
        source_provenance: Mapping[str, Any],
        value_key: str = "doses",
        unit: str = "doses",
    ) -> TemporalAnalyticsResult:
        start, end = _month(start_period), _month(end_period)
        if start > end:
            raise ValueError("start_period must not follow end_period")
        for name, value in (("source_series_ref", source_series_ref), ("value_key", value_key), ("unit", unit)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
        if value_key == "period":
            raise ValueError("value_key must differ from period")
        if not isinstance(source_provenance, Mapping):
            raise ValueError("source_provenance must be a JSON object")
        origin = deepcopy(dict(source_provenance))
        # Reject non-JSON metadata rather than silently stringify its meaning.
        json.dumps(origin, allow_nan=False)
        observed: dict[int, int | Decimal | None] = {}
        previous = None
        for row in rows:
            if not isinstance(row, Mapping) or "period" not in row or value_key not in row:
                raise ValueError("each row requires period and the selected value key")
            month = _month(row["period"])
            if previous is not None and month <= previous:
                raise ValueError("periods must be strictly ordered without duplicates")
            if not start <= month <= end:
                raise ValueError("row period is outside the requested interval")
            value = row[value_key]
            if value is not None and not (
                type(value) is int or isinstance(value, Decimal) and value.is_finite()
            ):
                raise ValueError("values must be int, finite Decimal or None; floats are not accepted")
            observed[month] = value
            previous = month

        output = []
        for month in range(start, end + 1):
            metrics = {}
            for order in FORMULAS:
                window = list(range(month - order, month + 1))
                reasons = []
                for dependency in window:
                    if dependency < start:
                        code = "INSUFFICIENT_HISTORY"
                    elif dependency not in observed:
                        code = "MISSING_MONTH"
                    elif observed[dependency] is None:
                        code = "MISSING_VALUE"
                    else:
                        continue
                    reasons.append({"code": code, "period": _period(dependency) if dependency >= 0 else None})
                metrics[f"delta_{order}"] = {
                    "classification": "DERIVED",
                    "value": None if reasons else _difference(
                        [observed[dependency] for dependency in reversed(window)], order
                    ),
                    "unavailable_reasons": reasons,
                }
            output.append({
                "period": _period(month),
                "value": observed.get(month),
                "observation_status": "MISSING_MONTH" if month not in observed else (
                    "MISSING_VALUE" if observed[month] is None else "OBSERVED"
                ),
                "metrics": metrics,
            })
        return TemporalAnalyticsResult(
            operation="temporal_finite_differences",
            data={"rows": output},
            provenance={
                "operation": "temporal_finite_differences",
                "classification": "DERIVED",
                "method": "backward_monthly_finite_difference",
                "method_version": METHOD_VERSION,
                "formulas": {f"delta_{order}": formula for order, formula in FORMULAS.items()},
                "period": {"start": start_period, "end": end_period, "inclusive": True},
                "parameters": {
                    "orders": [1, 2, 3], "step_months": 1,
                    "value_key": value_key, "missing_policy": "null_no_gap_crossing",
                    "alignment": "latest_month_backward_window",
                    "smoothing": None, "imputation": None,
                },
                "units": {f"delta_{order}": f"{unit}/month^{order}" for order in FORMULAS},
                "unit_convention": "discrete monthly step (h=1 month), not elapsed days",
                "numeric_encoding": "int as JSON number; Decimal as exact decimal string",
                "source_series_ref": source_series_ref,
                "source_provenance": origin,
                "microdata_sent_to_llm": False,
            },
            warnings=[
                "Finite differences are descriptive derived metrics; they do not establish causality, "
                "vaccination coverage, statistical anomalies or confirmed inflection points."
            ],
        )
