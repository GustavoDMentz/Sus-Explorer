import pytest
from pydantic import ValidationError

from sus_explorer.llm import guard_explicit_geography
from sus_explorer.schemas import QueryPlan


def plan(**kwargs):
    return QueryPlan(operation="count", year=2026, month=5, **kwargs)


def test_valid_plan_is_accepted():
    p = plan(uf="rs", municipality_code="431490", vaccine_code="9", age_min=0, age_max=200,
             vaccine_text="Influenza (trivalente)")
    assert p.uf == "RS"


@pytest.mark.parametrize("kwargs", [
    {"uf": "ZZ"},
    {"uf": "R" * 5000},
    {"municipality_code": "12"},
    {"municipality_code": "43149a"},
    {"vaccine_code": "9; DROP"},
    {"vaccine_text": "x" * 129},
    {"vaccine_text": "http://evil.example/x"},
    {"municipality_name": "Porto\x00Alegre"},
    {"municipality_name": "a​b"},          # zero-width (categoria Cf)
    {"age_min": -1},
    {"age_max": 201},
    {"age_min": 50, "age_max": 10},
    {"top_n": 0},
    {"top_n": 101},
    {"group_by": "x" * 33},
])
def test_out_of_bounds_fields_are_rejected_for_every_operation(kwargs):
    with pytest.raises(ValidationError):
        plan(**kwargs)


def test_clarification_plans_are_bounded_too():
    with pytest.raises(ValidationError):
        QueryPlan(status="needs_clarification", clarification_question="x" * 501)
    with pytest.raises(ValidationError):
        QueryPlan(status="needs_clarification", clarification_question="?", missing=["a"] * 21)


def test_geography_guard_asks_when_city_contradicts_uf():
    guarded = guard_explicit_geography("doses em Porto Alegre", plan(uf="SP", municipality_name="Porto Alegre"))
    assert guarded.status == "needs_clarification"
    assert "uf" in guarded.missing


def test_geography_guard_keeps_consistent_plan():
    p = plan(uf="RS", municipality_name="Porto Alegre")
    assert guard_explicit_geography("doses em Porto Alegre", p) is p
