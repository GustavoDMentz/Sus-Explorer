import pytest

from sus_explorer.analytics import temporal_query
from sus_explorer.text_safety import strip_remote_images


@pytest.mark.parametrize("text, expected", [
    ("veja ![logo](https://evil.example/p.png?id=1) aqui", "veja logo aqui"),
    ("![](https://evil.example/pixel.gif)", ""),
    ("![alt][ref]\n\n[ref]: https://evil.example/x.png", "alt\n\n[ref]: https://evil.example/x.png"),
    ('antes <img src="https://evil.example/x.png" onerror="x()"> depois', "antes  depois"),
    ("sem imagens, com [link](https://example.org) e **negrito**", "sem imagens, com [link](https://example.org) e **negrito**"),
])
def test_remote_images_are_removed_but_text_and_links_stay(text, expected):
    assert strip_remote_images(text) == expected


def test_non_string_is_returned_unchanged():
    assert strip_remote_images(None) is None


def test_short_environment_values_are_not_treated_as_secrets(monkeypatch):
    monkeypatch.setenv("MY_API_KEY", "1")
    monkeypatch.setenv("OTHER_TOKEN", "true")
    monkeypatch.setenv("REAL_SECRET", "a-long-secret-value")
    secrets = temporal_query._secrets()
    assert "1" not in secrets and "true" not in secrets
    assert "a-long-secret-value" in secrets
