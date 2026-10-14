"""Regressions for daily intent and bounded monthly query plans."""

from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from sus_explorer.pni import PNIRemote, months
from sus_explorer.schemas import (
    DAILY_QUERY_UNSUPPORTED,
    MAX_MONTHLY_INTERVAL_MONTHS,
    QueryPlan,
)
from sus_explorer.service import SUSExplorer


@pytest.mark.parametrize("operation", ["count", "group", "latency", "timeseries"])
def test_daily_plan_never_becomes_executable(operation):
    fields = {"year": 2026, "month": 5}
    if operation == "timeseries":
        fields = {"start_year": 2026, "start_month": 5,
                  "end_year": 2026, "end_month": 5}
    if operation == "group":
        fields["group_by"] = "sex"
    plan = QueryPlan(operation=operation, uf="RS", day=10, **fields)
    assert plan.status == "needs_clarification"
    assert plan.clarification_question == DAILY_QUERY_UNSUPPORTED

    backend = PNIRemote.__new__(PNIRemote)
    backend.dataset = Mock(side_effect=AssertionError("R2 must not be read"))
    for candidate in (plan, plan.model_copy(update={"status": "ready"})):
        with pytest.raises(ValueError, match="Consultas diárias"):
            backend.execute(candidate)
        with pytest.raises(ValueError, match="Consultas diárias"):
            getattr(backend, operation)(candidate)
    backend.dataset.assert_not_called()


@pytest.mark.parametrize("question", [
    "Quantas doses no dia 10 de maio de 2026?",
    "Quantas doses em 10 de maio de 2026?",
    "Quantas doses em 10/05/2026?",
    "Quantas doses por dia no RS?",
])
def test_explicit_daily_question_is_rejected_before_planning(question):
    explorer = SUSExplorer.__new__(SUSExplorer)
    explorer.llm = Mock()
    explorer.pni = Mock()
    response = explorer.ask(question)
    assert response["needs_clarification"] is True
    assert response["clarification_question"] == DAILY_QUERY_UNSUPPORTED
    assert response["result"] is None
    explorer.llm.plan.assert_not_called()
    explorer.pni.execute.assert_not_called()


def test_planner_day_is_rejected_even_without_a_recognized_daily_phrase():
    explorer = SUSExplorer.__new__(SUSExplorer)
    explorer.llm = Mock()
    explorer.llm.plan.return_value = QueryPlan(
        operation="count", uf="RS", year=2026, month=5, day=10,
    )
    explorer.pni = Mock()
    response = explorer.ask("Quantas doses foram aplicadas naquela data?")
    assert response["clarification_question"] == DAILY_QUERY_UNSUPPORTED
    explorer.pni.execute.assert_not_called()
    explorer.llm.answer.assert_not_called()


def test_monthly_question_with_greeting_still_reaches_planner():
    explorer = SUSExplorer.__new__(SUSExplorer)
    explorer.llm = Mock()
    explorer.llm.plan.return_value = QueryPlan(
        operation="count", uf="RS", year=2026, month=5,
    )
    explorer.llm.answer.return_value = "Resultado mensal"
    explorer.pni = Mock()
    explorer.pni.execute.return_value.model_dump.return_value = {"doses": 1}
    response = explorer.ask("Bom dia, quantas doses houve no RS em maio de 2026?")
    assert response["needs_clarification"] is False
    explorer.llm.plan.assert_called_once()
    explorer.pni.execute.assert_called_once()


@pytest.mark.parametrize("changes", [
    {"start_month": 0}, {"start_month": 13}, {"end_month": 0},
    {"end_month": 13}, {"start_year": 2026, "start_month": 7,
                        "end_year": 2026, "end_month": 6},
    {"start_year": 2023, "start_month": 12},
])
@pytest.mark.parametrize("operation", ["timeseries", "temporal"])
def test_invalid_or_excessive_monthly_interval_is_rejected(operation, changes):
    fields = {"operation": operation, "uf": "RS", "start_year": 2024,
              "start_month": 1, "end_year": 2026, "end_month": 12}
    if operation == "temporal":
        fields["temporal_analysis"] = {"order": 1}
    with pytest.raises(ValidationError):
        QueryPlan.model_validate(fields | changes)


@pytest.mark.parametrize("operation", ["timeseries", "temporal"])
def test_36_month_boundary_and_year_crossing_stay_valid(operation):
    fields = {"operation": operation, "uf": "RS", "start_year": 2024,
              "start_month": 1, "end_year": 2026, "end_month": 12}
    if operation == "temporal":
        fields["temporal_analysis"] = {"order": 1}
    plan = QueryPlan.model_validate(fields)
    assert plan.status == "ready"
    generated = list(months(2024, 1, 2026, 12))
    assert len(generated) == MAX_MONTHLY_INTERVAL_MONTHS
    assert generated[:2] == [(2024, 1), (2024, 2)]
    assert generated[-2:] == [(2026, 11), (2026, 12)]
    assert list(months(2025, 12, 2026, 2)) == [
        (2025, 12), (2026, 1), (2026, 2),
    ]


def test_inverted_years_are_rejected_even_before_months_are_known():
    with pytest.raises(ValidationError):
        QueryPlan(operation="timeseries", uf="RS", start_year=2027, end_year=2026)


@pytest.mark.parametrize("start_year,start_month,end_year,end_month", [
    (2026, 13, 2027, 1), (2026, 5, 2026, 4),
    (2023, 12, 2026, 12),
])
def test_month_generator_rejects_bad_ranges_instead_of_looping(
    start_year, start_month, end_year, end_month,
):
    with pytest.raises(ValueError):
        list(months(start_year, start_month, end_year, end_month))


def test_copied_invalid_plan_is_rechecked_before_r2():
    valid = QueryPlan(operation="timeseries", uf="RS", start_year=2026,
                      start_month=1, end_year=2026, end_month=6)
    backend = PNIRemote.__new__(PNIRemote)
    backend.dataset = Mock(side_effect=AssertionError("R2 must not be read"))
    for changed in (
        valid.model_copy(update={"start_month": 13}),
        valid.model_copy(update={"end_month": 0}),
        valid.model_copy(update={"start_month": 7}),
        valid.model_copy(update={"day": 10}),
    ):
        with pytest.raises((ValidationError, ValueError)):
            backend.execute(changed)
        with pytest.raises((ValidationError, ValueError)):
            backend.timeseries(changed)
    backend.dataset.assert_not_called()
