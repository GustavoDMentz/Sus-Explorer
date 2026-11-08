"""BYOK must not overwrite module-level credentials or share client instances."""
from dataclasses import replace
from unittest.mock import Mock

from sus_explorer.config import settings
from sus_explorer.legacy_r2_config import settings as legacy_settings
from sus_explorer.llm import OllamaAnalyst
from sus_explorer.pni import PNIRemote


def test_local_model_override_is_per_instance():
    client = Mock()
    analyst = OllamaAnalyst(model="test-model", client=client)
    assert analyst.client is client
    assert analyst.model == "test-model"
    assert not hasattr(settings, "gemini_api_key")


def test_r2_config_is_per_instance(monkeypatch):
    import sus_explorer.pni as module
    factory = Mock(side_effect=lambda **kwargs: Mock())
    monkeypatch.setattr(module.fs, "S3FileSystem", factory)
    first = replace(legacy_settings, r2_endpoint="https://first.invalid",
                    r2_access_key="first", r2_secret_key="secret-first",
                    r2_bucket="bucket-one")
    second = replace(legacy_settings, r2_endpoint="https://second.invalid",
                     r2_access_key="second", r2_secret_key="secret-second",
                     r2_bucket="bucket-two")
    a, b = PNIRemote(config=first), PNIRemote(config=second)
    assert a.path(2026, 5, "RS").startswith("bucket-one/")
    assert b.path(2026, 5, "RS").startswith("bucket-two/")
    assert a.s3 is not b.s3
    assert factory.call_count == 2
    assert legacy_settings.r2_access_key != "first"
