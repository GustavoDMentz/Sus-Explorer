import io
import json

import pytest

from sus_explorer import terminology
from sus_explorer.terminology import ImmunobiologicalTerminology


class FakeRaw(io.BytesIO):
    """urllib3 raw stream: read() accepts decode_content."""

    def read(self, amt=-1, decode_content=None):
        return super().read(amt)


def make(tmp_path):
    return ImmunobiologicalTerminology(cache_file=tmp_path / "terminology.json")


def test_corrupt_fresh_cache_is_treated_as_expired(tmp_path, monkeypatch):
    t = make(tmp_path)
    t.cache_file.write_text("{ not json", encoding="utf-8")          # recém-gravado, porém corrompido
    monkeypatch.setattr(t, "_download_and_merge", lambda: {"concepts": [], "from": "download"})
    assert t.load()["from"] == "download"


def test_valid_fresh_cache_is_used_without_download(tmp_path, monkeypatch):
    t = make(tmp_path)
    t.cache_file.write_text(json.dumps({"concepts": [], "from": "cache"}), encoding="utf-8")

    def no_network():
        raise AssertionError("não deveria baixar")
    monkeypatch.setattr(t, "_download_and_merge", no_network)
    assert t.load()["from"] == "cache"


def test_download_failure_with_corrupt_cache_raises_instead_of_inventing(tmp_path, monkeypatch):
    t = make(tmp_path)
    t.cache_file.write_text("garbage", encoding="utf-8")

    def fail():
        raise RuntimeError("sem rede")
    monkeypatch.setattr(t, "_download_and_merge", fail)
    with pytest.raises(RuntimeError):
        t.load(force_refresh=True)


def test_response_size_is_limited(monkeypatch):
    class Response:
        raw = FakeRaw(b"x" * (terminology.MAX_RESPONSE_BYTES + 10))

        def raise_for_status(self):
            pass

        def close(self):
            pass
    monkeypatch.setattr(terminology.requests, "get", lambda *a, **k: Response())
    with pytest.raises(ValueError, match="limite"):
        terminology._request_json("https://example.org/x")


def test_small_response_is_parsed(monkeypatch):
    class Response:
        raw = FakeRaw(b'{"ok": true}')

        def raise_for_status(self):
            pass

        def close(self):
            pass
    monkeypatch.setattr(terminology.requests, "get", lambda *a, **k: Response())
    assert terminology._request_json("https://example.org/x") == {"ok": True}
