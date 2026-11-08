"""BYOK must not overwrite module-level credentials or share client instances."""
from dataclasses import replace
from unittest.mock import Mock

from sus_explorer.config import settings
from sus_explorer.llm import GeminiAnalyst
from sus_explorer.pni import PNIRemote


def test_gemini_override_does_not_change_settings(monkeypatch):
    import sus_explorer.llm as module
    client = Mock()
    monkeypatch.setattr(module.genai, "Client", Mock(return_value=client))
    analyst = GeminiAnalyst(api_key="session-only-key", model="test-model")
    assert analyst.client is client
    assert analyst.model == "test-model"
    module.genai.Client.assert_called_once_with(api_key="session-only-key")
    assert settings.gemini_api_key != "session-only-key"


def test_r2_config_is_per_instance(monkeypatch):
    import sus_explorer.pni as module
    factory = Mock(side_effect=lambda **kwargs: Mock())
    monkeypatch.setattr(module.fs, "S3FileSystem", factory)
    first = replace(settings, r2_endpoint="https://first.invalid",
                    r2_access_key="first", r2_secret_key="secret-first",
                    r2_bucket="bucket-one")
    second = replace(settings, r2_endpoint="https://second.invalid",
                     r2_access_key="second", r2_secret_key="secret-second",
                     r2_bucket="bucket-two")
    a, b = PNIRemote(config=first), PNIRemote(config=second)
    assert a.path(2026, 5, "RS").startswith("bucket-one/")
    assert b.path(2026, 5, "RS").startswith("bucket-two/")
    assert a.s3 is not b.s3
    assert factory.call_count == 2
    assert settings.r2_access_key != "first"
