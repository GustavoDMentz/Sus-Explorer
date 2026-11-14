"""Shared query contract without an analytical storage dependency."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .schemas import QueryPlan, monthly_interval_months


@dataclass
class QueryResult:
    operation: str
    data: dict
    provenance: dict
    warnings: list[str] | None = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []

    def model_dump(self) -> dict:
        return asdict(self)


def require_ready_plan(plan: QueryPlan) -> QueryPlan:
    validated = QueryPlan.model_validate(plan.model_dump())
    if validated.status != "ready":
        raise ValueError(validated.clarification_question or "Plano precisa de esclarecimento.")
    return validated


def months(year: int, month: int, end_year: int, end_month: int):
    count = monthly_interval_months(year, month, end_year, end_month)
    start = year * 12 + month - 1
    for offset in range(count):
        current_year, zero_based_month = divmod(start + offset, 12)
        yield current_year, zero_based_month + 1
