"""Ollama planner and transport contracts without a running model."""
import json
from unittest.mock import Mock
import pytest
import requests

from sus_explorer.llm import OllamaAnalyst, PlannerResponseError, planner_output_schema
from sus_explorer.ollama import OllamaClient, OllamaError


def analyst(payload):
    client = Mock()
    client.chat.return_value = payload
    return OllamaAnalyst(model="test-model", client=client)


def test_planner_sends_schema_and_validates_response():
    llm = analyst('{"status":"ready","operation":"count","uf":"RS","year":2026,"month":5}')
    llm.deterministic_enabled = False
    plan = llm.plan("Quantas doses no RS em maio de 2026?")
    assert plan.operation == "count"
    assert llm.client.chat.call_args.kwargs["format"] == planner_output_schema()
    assert llm.last_planner_source == "ollama"


@pytest.mark.parametrize("payload", ["", "{", '{"operation":"arbitrary"}', '{"year":' + '9' * 65410 + '}'], ids=["empty", "truncated", "invalid", "oversized_integer"])
def test_invalid_output_is_rejected(payload):
    llm = analyst(payload)
    llm.deterministic_enabled = False
    with pytest.raises(PlannerResponseError):
        llm.plan("Contagem no RS em 2026")


def test_planner_retry_uses_json_mode():
    llm = analyst(None)
    llm.deterministic_enabled = False
    llm.client.chat.side_effect = ["{", '{"status":"ready","operation":"count","uf":"RS","year":2026}']
    assert llm.plan("Contagem no RS em 2026").year == 2026
    assert llm.client.chat.call_args.kwargs["format"] == "json"


def test_transport_failure_is_not_retried():
    llm = analyst(None)
    llm.deterministic_enabled = False
    llm.client.chat.side_effect = OllamaError("Ollama indisponível")
    with pytest.raises(OllamaError):
        llm.plan("Contagem no RS em 2026")
    llm.client.chat.assert_called_once()


@pytest.mark.parametrize("status,expected", [(404,"Modelo Ollama ausente"),(500,"HTTP 500")])
def test_http_errors(status, expected):
    client = OllamaClient()
    response = Mock(status_code=status, ok=False)
    client.session.post = Mock(return_value=response)
    with pytest.raises(OllamaError, match=expected):
        client.chat([{"role":"user","content":"a"}])


def test_connection_timeout_and_bad_response():
    client = OllamaClient()
    client.session.post = Mock(side_effect=requests.Timeout())
    with pytest.raises(OllamaError, match="tempo limite"):
        client.chat([{"role":"user","content":"a"}])
    client.session.post = Mock(side_effect=requests.ConnectionError())
    with pytest.raises(OllamaError, match="indisponível"):
        client.chat([{"role":"user","content":"a"}])
    client.session.post = Mock(return_value=Mock(status_code=200, ok=True, content=b"{}", json=lambda: {}))
    with pytest.raises(OllamaError, match="vazia"):
        client.chat([{"role":"user","content":"a"}])


def test_embedding_dimension_enforced():
    client = OllamaClient()
    client._request = Mock(return_value={"embeddings": [[0.0] * 8]})
    with pytest.raises(OllamaError, match="Dimensão"):
        client.embed(["texto"])


def test_embedding_model_digest_is_required():
    client = OllamaClient()
    client.session.get = Mock(return_value=Mock(ok=True, json=lambda: {"models": [
        {"name": "qwen3-embedding:0.6b", "digest": "sha256:abc"}]}))
    assert client.model_digest("qwen3-embedding:0.6b") == "sha256:abc"
    with pytest.raises(OllamaError, match="Modelo Ollama ausente"):
        client.model_digest("other")
