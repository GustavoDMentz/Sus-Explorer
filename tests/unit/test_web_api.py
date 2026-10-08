"""HTTP adapter contract tests; no Gemini or R2 network access."""
from unittest.mock import Mock

from fastapi.testclient import TestClient

import web_api


def test_health():
    response = TestClient(web_api.app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_passes_question_and_preserves_result(monkeypatch):
    expected = {"needs_clarification": False, "answer": "Agregado", "result": {
        "operation": "temporal", "data": {"rows": []},
        "provenance": {"classification": "DERIVED"}}}
    explorer = Mock()
    explorer.ask.return_value = expected
    monkeypatch.setattr(web_api, "explorer", lambda: explorer)
    response = TestClient(web_api.app).post("/api/ask", json={"question": "Variação mensal no RS?"})
    assert response.status_code == 200
    assert response.json() == expected
    explorer.ask.assert_called_once_with("Variação mensal no RS?")


def test_invalid_question_rejected():
    response = TestClient(web_api.app).post("/api/ask", json={"question": "a"})
    assert response.status_code == 422


def test_backend_failure_is_generic(monkeypatch):
    explorer = Mock()
    explorer.ask.side_effect = RuntimeError("PRIVATE_TOKEN=secret")
    monkeypatch.setattr(web_api, "explorer", lambda: explorer)
    response = TestClient(web_api.app).post("/api/ask", json={"question": "Quantas doses no RS?"})
    assert response.status_code == 503
    assert "secret" not in response.text


def test_temporal_failure_is_controlled(monkeypatch):
    from sus_explorer.analytics.temporal_query import TemporalQueryError
    explorer = Mock()
    explorer.ask.side_effect = TemporalQueryError("SOURCE_QUERY_FAILED", "Fonte indisponível.")
    monkeypatch.setattr(web_api, "explorer", lambda: explorer)
    response = TestClient(web_api.app).post("/api/ask", json={"question": "Aceleração no RS em 2026?"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "SOURCE_QUERY_FAILED"


def test_invalid_planner_response_is_controlled_and_does_not_execute_source(monkeypatch):
    from sus_explorer.llm import GeminiAnalyst, PlannerResponseError
    from sus_explorer.service import SUSExplorer
    import json
    service = SUSExplorer.__new__(SUSExplorer)
    service.llm = GeminiAnalyst.__new__(GeminiAnalyst)
    service.llm.model = 'offline-model'
    service.llm.client = Mock()
    def broken_sdk(**kwargs):
        return json.loads('{"year":' + '9' * 65410 + '}')
    service.llm.client.models.generate_content.side_effect = broken_sdk
    service.pni = Mock()
    monkeypatch.setattr(web_api, 'explorer', lambda: service)
    response = TestClient(web_api.app).post('/api/ask', json={
        'question':'Qual foi a variação mensal das doses no RS de janeiro a junho de 2026?'})
    assert response.status_code == 422
    assert response.json()['detail']['code'] == PlannerResponseError.code
    assert '65410' not in response.text
    service.pni.execute.assert_not_called()
