"""Deterministic finite differences for monthly aggregate dose counts.

This module does not access R2, PostgreSQL, or an LLM. Missing observations
break difference chains; they are never interpreted as zero.
"""
from __future__ import annotations

from datetime import date
from typing import Sequence


def _month(value: str) -> date:
    if not isinstance(value, str) or len(value) != 7 or value[4] != "-":
        raise ValueError("month must use YYYY-MM")
    try:
        parsed = date.fromisoformat(value + "-01")
    except ValueError as exc:
        raise ValueError("month must use a valid YYYY-MM") from exc
    if parsed.strftime("%Y-%m") != value:
        raise ValueError("month must use YYYY-MM")
    return parsed


def _next_month(value: date) -> date:
    return date(value.year + (value.month == 12), value.month % 12 + 1, 1)


def monthly_differences(
    observations: Sequence[tuple[str, int | None]],
    *,
    source_provenance: dict | None = None,
) -> dict:
    """Compute backward differences up to order three.

    Each input pair is (YYYY-MM, monthly_doses). Input months must be strictly
    increasing, but may have gaps. None is missing, whereas 0 is an observed
    zero. Differences require consecutive calendar months with observed values.
    The third difference is descriptive, not an anomaly detector.
    """
    if isinstance(observations, (str, bytes)):
        raise ValueError("observations must be a sequence of month/count pairs")
    rows: list[dict] = []
    previous: date | None = None
    for item in observations:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError("each observation must be a month/count pair")
        month, count = item
        parsed = _month(month)
        if previous is not None and parsed <= previous:
            raise ValueError("months must be strictly increasing and unique")
        if count is not None and (type(count) is not int or count < 0):
            raise ValueError("monthly doses must be nonnegative integers or None")
        rows.append({"month": month, "doses": count, "d1": None, "d2": None, "d3": None})
        previous = parsed

    for i in range(1, len(rows)):
        if _next_month(_month(rows[i - 1]["month"])) != _month(rows[i]["month"]):
            continue
        left, right = rows[i - 1], rows[i]
        if left["doses"] is not None and right["doses"] is not None:
            right["d1"] = right["doses"] - left["doses"]
        if left["d1"] is not None and right["d1"] is not None:
            right["d2"] = right["d1"] - left["d1"]
        if left["d2"] is not None and right["d2"] is not None:
            right["d3"] = right["d2"] - left["d2"]

    if source_provenance is not None and not isinstance(source_provenance, dict):
        raise ValueError("source_provenance must be a dictionary or None")
    return {
        "classification": "DERIVED",
        "granularity": "calendar_month",
        "rows": rows,
        "provenance": {
            "method": "backward_finite_difference",
            "method_version": 1,
            "formulas": {
                "d1": "y[t]-y[t-1]",
                "d2": "y[t]-2*y[t-1]+y[t-2]",
                "d3": "y[t]-3*y[t-1]+3*y[t-2]-y[t-3]",
            },
            "units": {"doses": "doses/month", "d1": "doses/month^2", "d2": "doses/month^3", "d3": "doses/month^4"},
            "period_start": rows[0]["month"] if rows else None,
            "period_end": rows[-1]["month"] if rows else None,
            "source": dict(source_provenance or {}),
            "limitations": [
                "Calendar months have unequal lengths; differences use one calendar-month step.",
                "Missing months and missing counts break difference chains.",
                "Finite differences alone do not establish epidemiological causality, statistical significance, or anomalies.",
            ],
        },
    }
