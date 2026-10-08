from copy import deepcopy
from decimal import Decimal
import json
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.dataset as ds
import pytest
from pydantic import ValidationError

from sus_explorer.analytics.temporal_query import (
    SOURCE_LABEL, TemporalQueryError, execute_temporal, temporal_answer_payload,
)
from sus_explorer.llm import ANSWER, PLANNER, GeminiAnalyst
from sus_explorer.pni import PNIRemote, QueryResult
from sus_explorer.schemas import QueryPlan, TemporalRequest
from sus_explorer.service import SUSExplorer


def plan(order=2, **kwargs):
    return QueryPlan.model_validate({
        "operation": "temporal", "uf": "RS", "start_year": 2026, "start_month": 1,
        "end_year": 2026, "end_month": 6, "temporal_analysis": {"order": order},
    } | kwargs)


def source(values, periods=None, provenance=None):
    periods = periods or [f"2026-{index + 1:02d}" for index in range(len(values))]
    return QueryResult("timeseries", {"rows": [
        {"period": period, "doses": value} for period, value in zip(periods, values)
    ]}, provenance if provenance is not None else {
        "source": SOURCE_LABEL, "uf_partition": "RS", "partitions_consulted": len(values),
        "missing_partitions": [], "parquet_fragments": 3, "microdata_sent_to_llm": False,
    })


def run(values, order=2, periods=None, **kwargs):
    return execute_temporal(plan(order, **kwargs), lambda _: source(values, periods))


def values(result, order):
    return [row["metrics"][f"delta_{order}"]["value"] for row in result.data["rows"]]


@pytest.mark.parametrize("order", [1, 2, 3])
def test_typed_orders_and_schema(order):
    p = plan(order)
    assert p.temporal_analysis == TemporalRequest(order=order)
    assert p.status == "ready"
    assert p.temporal_analysis.metric == "doses"
    assert p.temporal_analysis.granularity == "monthly"


@pytest.mark.parametrize("order", [0, 4, True, "2", 2.0, None])
def test_invalid_order_rejected(order):
    with pytest.raises(ValidationError):
        plan(order)


@pytest.mark.parametrize("changes", [
    {"temporal_analysis": {"order": 2, "metric": "coverage"}},
    {"temporal_analysis": {"order": 2, "granularity": "daily"}},
    {"temporal_analysis": {"order": 2, "sql": "DROP TABLE x"}},
    {"start_month": 0}, {"end_month": 13}, {"start_year": 2019},
    {"start_year": "2026"}, {"start_month": True},
    {"start_month": 7}, {"uf": "XX"}, {"day": 1}, {"year": 2026},
    {"group_by": "vaccine"}, {"age_min": -1}, {"age_min": 9, "age_max": 2},
    {"municipality_code": "private-user-id"},
    {"municipality_code": "4314902", "municipality_name": "Porto Alegre"},
    {"vaccine_text": "https://user:password@example.com"},
    {"vaccine_code": "inferred"}, {"sql": "SELECT * FROM patient"},
    {"top_n": 10},
])
def test_invalid_temporal_parameters_rejected(changes):
    with pytest.raises(ValidationError):
        plan(**changes)


@pytest.mark.parametrize("missing", ["uf", "start_year", "start_month", "end_year", "end_month", "temporal_analysis"])
def test_missing_parameters_become_clarification_without_invention(missing):
    p = plan(**{missing: None})
    assert p.status == "needs_clarification"
    assert missing in p.missing
    assert getattr(p, missing) is None
    assert p.clarification_question
    with pytest.raises(TemporalQueryError, match="incompleto"):
        execute_temporal(p, lambda _: pytest.fail("must not query incomplete plan"))


@pytest.mark.parametrize("operation", ["count", "group", "timeseries", "latency"])
def test_legacy_plans_roundtrip_and_dispatch(operation):
    payload = {"operation": operation, "uf": "rs", "year": 2026, "month": None,
               "start_year": 2026, "start_month": 1, "end_year": 2026, "end_month": 6}
    p = QueryPlan.model_validate(payload)
    assert p.uf == "RS" and p.month is None
    assert QueryPlan.model_validate(p.model_dump()) == p
    backend = PNIRemote.__new__(PNIRemote)
    calls = []
    expected = QueryResult(operation, {"unchanged": True}, {"original": True})
    for name in ("count", "group", "timeseries", "latency"):
        setattr(backend, name, lambda passed, name=name: calls.append((name, passed)) or expected)
    assert backend.execute(p) is expected
    assert calls == [(operation, p)]


@pytest.mark.parametrize("operation", ["count", "group", "timeseries", "latency"])
def test_temporal_parameters_not_ignored_on_legacy_operation(operation):
    with pytest.raises(ValidationError):
        QueryPlan(operation=operation, temporal_analysis={"order": 1})


@pytest.mark.parametrize("power,order,expected", [
    (0, 1, [None, 0, 0, 0, 0, 0]),
    (1, 1, [None, 1, 1, 1, 1, 1]),
    (2, 2, [None, None, 2, 2, 2, 2]),
    (3, 3, [None, None, None, 6, 6, 6]),
])
def test_integrated_polynomial_series(power, order, expected):
    result = run([t**power for t in range(6)], order)
    assert values(result, order) == expected
    assert all(list(row["metrics"]) == [f"delta_{order}"] for row in result.data["rows"])


def test_executor_reuses_timeseries_and_preserves_all_supported_filters():
    backend = PNIRemote.__new__(PNIRemote)
    captured = []
    p = plan(2, municipality_name="Porto Alegre", vaccine_text="influenza", sex="F", age_min=20, age_max=40)
    original = source([10, 15, 18, 20])
    before = deepcopy(original.model_dump())
    backend.timeseries = lambda passed: captured.append(passed) or original
    result = backend.execute(p)
    assert len(captured) == 1
    passed = captured[0]
    assert passed.operation == "timeseries" and passed.temporal_analysis is None
    for field in ("uf", "municipality_name", "vaccine_text", "sex", "age_min", "age_max", "start_year", "end_month"):
        assert getattr(passed, field) == getattr(p, field)
    assert original.model_dump() == before
    assert result.provenance["source_provenance"] == original.provenance
    assert result.provenance["filters"]["vaccine_text"] == "influenza"


def test_adapter_uses_real_monthly_aggregation_and_filters_without_llm_or_network():
    backend = PNIRemote.__new__(PNIRemote)
    table = pa.table({
        "co_municipio_estabelecimento": ["4314902", "4314902", "4304606"],
        "ds_vacina": ["INFLUENZA", "OUTRA", "INFLUENZA"],
        "tp_sexo_paciente": ["F", "F", "M"], "nu_idade_paciente": [30, 10, 30],
    })
    backend.dataset = lambda *_: ds.dataset(table)
    p = plan(1, municipality_code="4314902", vaccine_text="influenza", sex="F", age_min=20)
    result = backend.execute(p)
    assert [row["value"] for row in result.data["rows"]] == [1] * 6
    assert values(result, 1) == [None, 0, 0, 0, 0, 0]


def test_missing_and_null_months_block_every_order_and_remain_distinct():
    result = run([0, None, 4, 5, 6], 2, ["2026-01", "2026-02", "2026-04", "2026-05", "2026-06"])
    assert values(result, 2) == [None, None, None, None, None, 0]
    assert result.data["rows"][1]["observation_status"] == "MISSING_VALUE"
    assert result.data["rows"][2]["observation_status"] == "MISSING_MONTH"
    assert result.data["rows"][2]["value"] is None


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_insufficient_history_does_not_fetch_preceding_observations(count):
    captured = []
    result = execute_temporal(plan(3), lambda p: captured.append(p) or source(list(range(count))))
    assert all(value is None for value in values(result, 3))
    assert len(captured) == 1 and captured[0].start_month == 1


def test_year_boundary():
    result = run([8, 6, 4, 2], 1, ["2025-11", "2025-12", "2026-01", "2026-02"], start_year=2025, start_month=11, end_month=2)
    assert values(result, 1) == [None, -2, -2, -2]


def test_exact_decimal_and_large_integer_integration():
    result = run([10**100 + t**3 for t in range(6)], 3)
    assert values(result, 3) == [None, None, None, 6, 6, 6]
    result = run([Decimal("0.1"), Decimal("0.3"), Decimal("0.6")], 2, end_month=3)
    assert values(result, 2) == [None, None, Decimal("0.1")]
    assert result.model_dump()["data"]["rows"][2]["metrics"]["delta_2"]["value"] == "0.1"


def test_provenance_reference_is_reproducible_and_sensitive_to_data_and_filters():
    first = run([1, 3, 8], 2)
    second = run([1, 3, 8], 2)
    assert first.provenance == second.provenance
    ref = first.provenance["source_series_ref"]
    assert ref.startswith("timeseries:sha256:") and len(ref.split(":")[-1]) == 64
    assert ref != run([1, 3, 9], 2).provenance["source_series_ref"]
    assert ref != run([1, 3, 8], 2, sex="F").provenance["source_series_ref"]
    provenance = first.provenance
    assert provenance["classification"] == "DERIVED"
    assert provenance["source_classification"] == "DIRECT"
    assert provenance["order"] == 2 and provenance["granularity"] == "monthly"
    assert provenance["method_version"] == "1.0.0"
    assert provenance["formula"] == "y(t) - 2*y(t-1) + y(t-2)"
    assert provenance["units"] == {"delta_2": "doses/month^2"}
    assert provenance["parameters"]["orders"] == [2]
    assert all(row["observation_classification"] == "DIRECT" for row in first.data["rows"])


def test_deceleration_can_coexist_with_increasing_monthly_volume():
    result = run([10, 15, 18, 20], 2, end_month=4)
    assert values(result, 2) == [None, None, -2, -1]
    assert [row["value"] for row in result.data["rows"]] == [10, 15, 18, 20]
    assert result.data["rows"][-1]["metrics"]["delta_2"]["interpretation"] == "MONTHLY_CHANGE_DECREASING"
    assert "NÃO implica necessariamente queda" in ANSWER
    assert "Nunca recalcule, corrija ou substitua" in ANSWER


@pytest.mark.parametrize("order,values_in,label", [
    (1, [2, 1], "MONTHLY_VOLUME_DECREASING"),
    (1, [1, 2], "MONTHLY_VOLUME_INCREASING"),
    (1, [0, 0], "MONTHLY_VOLUME_UNCHANGED"),
    (2, [0, 1, 4], "MONTHLY_CHANGE_INCREASING"),
    (3, [0, 1, 8, 27], "SECOND_DIFFERENCE_INCREASING"),
])
def test_interpretation_tags(order, values_in, label):
    result = run(values_in, order, end_month=len(values_in))
    assert result.data["rows"][-1]["metrics"][f"delta_{order}"]["interpretation"] == label


@pytest.mark.parametrize("bad_rows", [
    [{"period": "2026-01", "doses": 1.0}],
    [{"period": "2026-01", "doses": "1"}],
    [{"period": "2026-01"}],
    [{"period": "2026-01", "doses": True}],
    [{"period": "2026-01", "doses": 1}] * 2,
    [{"period": "2026-02", "doses": 1}, {"period": "2026-01", "doses": 1}],
])
def test_malformed_source_series_fail_safely(bad_rows):
    with pytest.raises(TemporalQueryError) as error:
        execute_temporal(plan(), lambda _: QueryResult("timeseries", {"rows": bad_rows}, {}))
    assert error.value.code == "INVALID_SOURCE_SERIES"


@pytest.mark.parametrize("exception", [FileNotFoundError, KeyError, RuntimeError])
def test_source_failures_hide_raw_exception_and_do_not_call_llm(exception):
    def fail(_):
        raise exception("patient@example.com password=secret private-id=123")
    with pytest.raises(TemporalQueryError) as error:
        execute_temporal(plan(), fail)
    assert error.value.code == "SOURCE_QUERY_FAILED"
    assert "secret" not in str(error.value) and "private-id" not in str(error.value)


def test_all_partitions_unavailable_using_real_timeseries_is_controlled_failure():
    backend = PNIRemote.__new__(PNIRemote)
    def unavailable(*_):
        raise FileNotFoundError("private-location")
    backend.dataset = unavailable
    with pytest.raises(TemporalQueryError) as error:
        backend.execute(plan())
    assert error.value.code == "SOURCE_QUERY_FAILED"


@pytest.mark.parametrize("provenance", [
    {"microdata_sent_to_llm": True},
    {"uf_partition": "SP"},
    {"missing_partitions": ["ano=2026/mes=01/uf=RS"]},
    {"missing_partitions": ["ano=2027/mes=01/uf=RS"]},
    {"missing_partitions": ["private-object"]},
])
def test_inconsistent_source_metadata_is_not_presented(provenance):
    with pytest.raises(TemporalQueryError) as error:
        execute_temporal(plan(), lambda _: source([1, 3], provenance=provenance))
    assert error.value.code == "INVALID_SOURCE_SERIES"


def test_real_timeseries_missing_partitions_are_preserved():
    backend = PNIRemote.__new__(PNIRemote)
    def monthly(year, month, uf):
        if month == 2:
            raise FileNotFoundError("unavailable")
        return ds.dataset(pa.table({"x": [month]}))
    backend.dataset = monthly
    result = backend.execute(plan(1))
    assert result.provenance["source_provenance"]["missing_partitions"] == ["ano=2026/mes=02/uf=RS"]
    assert values(result, 1) == [None, None, None, 0, 0, 0]


def test_sanitization_drops_microdata_private_metadata_and_preserves_origin(monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN", "known-secret")
    origin = source([1, 3, 7])
    origin.data["rows"][0]["patient"] = {"cpf": "123.456.789-00"}
    origin.data["raw_records"] = [{"cns": "private-cns"}]
    origin.provenance.update({"url": "https://user:pass@example.com/x?X-Amz-Signature=abc",
                              "private_id": "private-object", "nested": {"token": "known-secret"}})
    before = deepcopy(origin.model_dump())
    result = execute_temporal(plan(), lambda _: origin)
    dumped = json.dumps(result.model_dump())
    payload = json.dumps(temporal_answer_payload(plan(), result))
    for secret in ("123.456.789-00", "private-cns", "user:pass", "Signature", "private-object", "known-secret", "raw_records"):
        assert secret not in dumped and secret not in payload
    assert origin.model_dump() == before


class Models:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def analyst(response):
    llm = GeminiAnalyst.__new__(GeminiAnalyst)
    llm.model = "mock"
    llm.client = SimpleNamespace(models=Models(response))
    return llm


@pytest.mark.parametrize("question,order,phrase", [
    ("Qual foi a variação mensal das doses no RS de janeiro a junho de 2026?", 1, "variação mensal"),
    ("A vacinação contra influenza no RS está acelerando de janeiro a junho de 2026?", 2, "acelerando"),
    ("O crescimento das doses no RS está perdendo força de janeiro a junho de 2026?", 2, "crescimento perdendo força"),
    ("Qual a mudança da aceleração no RS de janeiro a junho de 2026?", 3, "mudança da aceleração"),
])
def test_planner_intent_contract_with_mocked_gemini(question, order, phrase):
    expected = plan(order)
    llm = analyst(SimpleNamespace(parsed=expected.model_dump()))
    actual = llm.plan(question)
    assert actual == expected
    call = llm.client.models.calls[0]
    assert question in call["contents"] and phrase in PLANNER
    assert call["config"].response_schema is None
    assert call["config"].response_json_schema == QueryPlan.model_json_schema()
    assert call["config"].automatic_function_calling.disable is True


def test_planner_text_fallback_and_clarification():
    expected = plan(2, start_year=None, start_month=None, end_year=None, end_month=None)
    llm = analyst(SimpleNamespace(parsed=None, text=expected.model_dump_json()))
    actual = llm.plan("A vacinação contra influenza no RS está acelerando?")
    assert actual.status == "needs_clarification"
    assert actual.start_year is None and actual.end_year is None


def test_answer_receives_only_sanitized_aggregates_and_no_free_user_text():
    llm = analyst(SimpleNamespace(text="A variação mensal diminuiu; o volume ainda cresceu."))
    p = plan(2, end_month=4)
    result = execute_temporal(p, lambda _: source([10, 15, 18, 20]))
    response = llm.answer("CPF 123.456.789-00 patient@example.com", p, result)
    assert "volume ainda cresceu" in response
    contents = llm.client.models.calls[0]["contents"]
    assert "patient@example.com" not in contents and "123.456.789-00" not in contents
    assert '"classification": "DERIVED"' in contents
    assert '"observation_classification": "DIRECT"' in contents
    assert '"value": -1' in contents
    assert '"microdata_sent_to_llm": false' in contents


def test_natural_language_service_end_to_end_with_mocks():
    p = plan(2, end_month=4, vaccine_text="influenza")
    explorer = SUSExplorer.__new__(SUSExplorer)
    backend = PNIRemote.__new__(PNIRemote)
    backend.timeseries = lambda _: source([10, 15, 18, 20])
    explorer.pni = backend
    calls = []
    explorer.llm = SimpleNamespace(plan=lambda _: p, answer=lambda q, p, result: calls.append(result) or "Variação mensal diminuindo.")
    response = explorer.ask("A vacinação contra influenza no RS está acelerando de janeiro a abril de 2026?")
    assert not response["needs_clarification"]
    assert response["result"]["operation"] == "temporal"
    assert response["result"]["provenance"]["classification"] == "DERIVED"
    assert values(calls[0], 2) == [None, None, -2, -1]


def test_service_clarification_avoids_query_and_answer():
    explorer = SUSExplorer.__new__(SUSExplorer)
    explorer.llm = SimpleNamespace(plan=lambda _: plan(2, uf=None), answer=lambda *_: pytest.fail("must not explain"))
    explorer.pni = SimpleNamespace(execute=lambda _: pytest.fail("must not query"))
    response = explorer.ask("Como mudou a aceleração ao longo de 2026?")
    assert response["needs_clarification"] and response["result"] is None
    assert "uf" in response["missing_internal"]


def test_service_failure_never_explains_an_unavailable_result():
    explorer = SUSExplorer.__new__(SUSExplorer)
    backend = PNIRemote.__new__(PNIRemote)
    def fail(_):
        raise FileNotFoundError("private")
    backend.timeseries = fail
    explorer.pni = backend
    explorer.llm = SimpleNamespace(plan=lambda _: plan(), answer=lambda *_: pytest.fail("must not explain failure"))
    with pytest.raises(TemporalQueryError):
        explorer.ask("Aceleração no RS de janeiro a junho de 2026")
