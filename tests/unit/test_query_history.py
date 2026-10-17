from unittest.mock import Mock
from uuid import UUID

from sus_explorer.data.persistence.history import safe_parameters, safe_provenance
from sus_explorer.pni import QueryResult
from sus_explorer.schemas import QueryPlan
from sus_explorer.service import SUSExplorer


def test_history_metadata_omits_free_text_and_results():
    plan = QueryPlan(operation="count", year=2026, month=5, uf="RS",
                     vaccine_text="nome privado", municipality_name="nome privado")
    result = QueryResult("count", {"doses": 17}, {
        "source": "R2", "period": "2026-05",
        "partitions": ["ano=2026/mes=05/uf=RS"],
        "vaccine_filter": {"requested_text": "nome privado"},
    })
    assert safe_parameters(plan) == {"year": 2026, "month": 5, "uf": "RS", "top_n": 20}
    assert safe_provenance(result) == {
        "period": "2026-05", "partitions": ["ano=2026/mes=05/uf=RS"]
    }


def test_success_reports_unavailable_history_without_hiding_analytical_result(monkeypatch):
    import sus_explorer.service as module

    service = SUSExplorer.__new__(SUSExplorer)
    service.history_enabled = True
    service.llm = Mock()
    service.llm.plan.return_value = QueryPlan(operation="count", year=2026, month=5, uf="RS")
    service.llm.answer.return_value = "17 doses."
    service.pni = Mock()
    service.executor = Mock()
    service.executor.execute.return_value = QueryResult("count", {"doses": 17}, {"source": "R2"})

    def unavailable(**kwargs):
        assert isinstance(kwargs["query_id"], UUID)
        assert kwargs["executor"] == "r2"
        assert kwargs["provenance"] == {}
        raise RuntimeError("database offline")

    monkeypatch.setattr(module, "record_query", unavailable)
    response = service.ask("Pergunta agregada")
    assert response["result"]["data"] == {"doses": 17}
    assert response["history_status"] == "unavailable"


def test_failed_execution_attempt_is_recorded_without_question(monkeypatch):
    import pytest
    import sus_explorer.service as module

    service = SUSExplorer.__new__(SUSExplorer)
    service.history_enabled = True
    service.llm = Mock()
    service.llm.plan.return_value = QueryPlan(operation="count", year=2026, month=5, uf="RS")
    service.pni = Mock()
    service.executor = Mock()
    service.executor.execute.side_effect = RuntimeError("R2 offline")
    recorded = []
    monkeypatch.setattr(module, "record_query", lambda **kwargs: recorded.append(kwargs))
    with pytest.raises(RuntimeError, match="R2 offline"):
        service.ask("Pergunta com possível dado pessoal")
    assert len(recorded) == 1
    assert recorded[0]["status"] == "FAILED"
    assert recorded[0]["executor"] == "unknown"
    assert "Pergunta" not in str(recorded[0])
