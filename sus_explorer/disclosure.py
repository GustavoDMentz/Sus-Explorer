"""Statistical disclosure control for the counts shown to users.

Rules (documented in docs/privacy.md):

* A positive count below ``MIN_CELL_COUNT`` is suppressed and shown as "menos de 5".
  Zero is not a small cell: it says nothing about any person.
* Complementary suppression: a breakdown never shows a total from which a suppressed
  cell could be recovered by subtraction. When the hidden remainder (total minus the
  visible cells) is positive but below the threshold, the total is hidden too.
* Latency percentiles over fewer than the threshold of records are suppressed, since
  with so few records a percentile is an individual value.
* Age filters and the age breakdown use 5-year bands, never exact ages.
* Temporal series: a suppressed month becomes an unavailable observation, so the
  existing "no differences across gaps" rule also blocks reconstructing it from deltas.

Successive different queries can still be combined (the residual risk is documented);
bands and suppression make that costly, not impossible.
"""
from __future__ import annotations

import os

DEFAULT_MIN_CELL_COUNT = 5
LABEL = "menos de 5"
AGE_BAND_YEARS = 5
MAX_AGE = 200
SUPPRESSION_WARNING = (
    "Valores menores que {k} foram suprimidos para proteger a privacidade; "
    "o total também pode ter sido ocultado para que não seja possível recuperá-los por subtração."
)
AGE_WARNING = (
    "A faixa etária foi ajustada para {low}–{high} anos (faixas de {width} anos) "
    "para proteger a privacidade."
)


def configured_min_cell_count(explicit: int | None = None) -> int:
    """Threshold from code or ``SUS_MIN_CELL_COUNT``; it can be raised, never below 5."""
    raw = explicit if explicit is not None else os.getenv("SUS_MIN_CELL_COUNT")
    if raw is None or raw == "":
        return DEFAULT_MIN_CELL_COUNT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError("SUS_MIN_CELL_COUNT deve ser inteiro") from None
    if value < DEFAULT_MIN_CELL_COUNT:
        raise ValueError(f"SUS_MIN_CELL_COUNT não pode ser menor que {DEFAULT_MIN_CELL_COUNT}")
    return value


def is_small(count, k: int) -> bool:
    return isinstance(count, int) and not isinstance(count, bool) and 0 < count < k


def snap_age_range(age_min: int | None, age_max: int | None) -> tuple[int | None, int | None, bool]:
    """Widen an age filter to whole 5-year bands. Returns (min, max, changed)."""
    low, high = age_min, age_max
    if age_min is not None:
        low = (age_min // AGE_BAND_YEARS) * AGE_BAND_YEARS
    if age_max is not None:
        high = min(((age_max // AGE_BAND_YEARS) + 1) * AGE_BAND_YEARS - 1, MAX_AGE)
    return low, high, (low, high) != (age_min, age_max)


def age_warning(low: int | None, high: int | None) -> str:
    return AGE_WARNING.format(low=0 if low is None else low,
                              high="+" if high is None else high, width=AGE_BAND_YEARS)


def suppress_count(data: dict, k: int) -> int:
    count = data.get("doses")
    if is_small(count, k):
        data.update(doses=None, suppressed=True, count_display=LABEL)
        return 1
    return 0


def suppress_timeseries(data: dict, k: int) -> int:
    suppressed = 0
    for row in data.get("rows", []):
        if is_small(row.get("doses"), k):
            row["doses"] = None
            suppressed += 1
    return suppressed


def suppress_groups(data: dict, k: int) -> int:
    rows = data.get("rows", [])
    suppressed = 0
    for row in rows:
        if is_small(row.get("count"), k):
            row.update(count=None, count_display=LABEL, suppressed=True)
            suppressed += 1
    total = data.get("total_after_filters")
    if isinstance(total, int):
        shown = sum(row["count"] for row in rows if isinstance(row.get("count"), int))
        hidden = total - shown
        # hidden == 0: nothing was withheld. hidden >= k: no single withheld cell is
        # recoverable. Otherwise the total would reveal a small remainder.
        if hidden != 0 and hidden < k:
            data["total_after_filters"] = None
            data["total_suppressed"] = True
            suppressed += 0 if suppressed else 1
    return suppressed


def suppress_latency(data: dict, k: int) -> int:
    if is_small(data.get("n_valid"), k):
        data.update(n_valid=None, median_days=None, p90_days=None, p95_days=None,
                    suppressed=True, count_display=LABEL)
        return 1
    return 0


def apply(operation: str, data: dict, k: int) -> int:
    """Suppress small cells in ``data`` in place; return the number of suppressions."""
    handlers = {"count": suppress_count, "timeseries": suppress_timeseries,
                "group": suppress_groups, "latency": suppress_latency}
    return handlers[operation](data, k)
