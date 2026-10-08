"""Gemini planner structured-output contract (offline, no API key or network)."""
from unittest.mock import Mock
import pytest
from google.genai import types
from sus_explorer.llm import GeminiAnalyst
from sus_explorer.schemas import QueryPlan


def _analyst_with_fake_client(payload):
    analyst = GeminiAnalyst.__new__(GeminiAnalyst)
    analyst.model = "test-model"
    analyst.client = Mock()
    analyst.client.models.generate_content.return_value = Mock(parsed=None, text=payload)
    return analyst


def test_planner_sends_native_json_schema_and_validates_response():
    analyst = _analyst_with_fake_client('{"status":"ready","operation":"count","uf":"RS","year":2026,"month":5}')
    plan = analyst.plan("Quantas doses no RS em maio de 2026?")
    assert isinstance(plan, QueryPlan)
    assert plan.operation == "count"
    config = analyst.client.models.generate_content.call_args.kwargs["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert config.response_mime_type == "application/json"
    assert config.response_schema is None
    assert config.response_json_schema == QueryPlan.model_json_schema()
    assert config.automatic_function_calling.disable is True


def test_planner_keeps_strict_local_pydantic_validation():
    analyst = _analyst_with_fake_client('{"status":"ready","operation":"temporal","uf":"RS","start_year":2026,"start_month":1,"end_year":2026,"end_month":6,"temporal_analysis":{"order":4}}')
    import pytest
    with pytest.raises(ValueError):
        analyst.plan("Terceira diferença no RS em 2026")


def test_native_schema_preserves_additional_properties_in_json_schema():
    schema = QueryPlan.model_json_schema()
    assert schema["$defs"]["TemporalRequest"]["additionalProperties"] is False
    analyst = _analyst_with_fake_client('{"status":"ready","operation":"count","uf":"RS","year":2026}')
    analyst.plan("Contagem no RS em 2026")
    sent = analyst.client.models.generate_content.call_args.kwargs["config"].response_json_schema
    assert sent["$defs"]["TemporalRequest"]["additionalProperties"] is False


def test_sdk_excessive_integer_is_controlled_without_disabling_guard():
    import json
    import sys
    import pytest
    from sus_explorer.llm import PlannerResponseError, PLANNER_MAX_OUTPUT_TOKENS
    analyst = _analyst_with_fake_client(None)
    limit = sys.get_int_max_str_digits()
    def sdk_parse(**kwargs):
        assert kwargs['config'].max_output_tokens == PLANNER_MAX_OUTPUT_TOKENS
        # Reproduce the SDK's json.loads failure before returning a response.
        return json.loads('{"year":' + '9' * 65410 + '}')
    analyst.client.models.generate_content.side_effect = sdk_parse
    with pytest.raises(PlannerResponseError) as error:
        analyst.plan('Variação no RS em 2026?')
    assert error.value.code == 'INVALID_PLANNER_RESPONSE'
    assert '65410' not in str(error.value)
    assert error.value.__suppress_context__
    assert sys.get_int_max_str_digits() == limit


@pytest.mark.parametrize('payload', ['', '{', '{"year":' + '9' * 65410 + '}',
                                     '{"operation":"arbitrary"}'])
def test_invalid_or_oversized_text_is_rejected(payload):
    from sus_explorer.llm import PlannerResponseError
    with pytest.raises(PlannerResponseError):
        _analyst_with_fake_client(payload).plan('Contagem no RS em 2026')


def test_truncated_response_is_rejected_even_with_valid_parsed_plan():
    from types import SimpleNamespace
    from sus_explorer.llm import PlannerResponseError
    analyst = _analyst_with_fake_client('{}')
    analyst.client.models.generate_content.return_value = SimpleNamespace(
        parsed={'operation':'count','uf':'RS','year':2026}, text='{}',
        candidates=[SimpleNamespace(finish_reason=types.FinishReason.MAX_TOKENS)])
    with pytest.raises(PlannerResponseError):
        analyst.plan('Contagem no RS em 2026')
