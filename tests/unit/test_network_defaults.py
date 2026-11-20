import threading

import pytest
import requests

from sus_explorer import ollama
from sus_explorer.data.persistence import database


def base_env(monkeypatch, host, sslmode=None):
    for name, value in {"POSTGRES_HOST": host, "POSTGRES_PORT": "5432", "POSTGRES_DB": "d",
                        "POSTGRES_USER": "u", "POSTGRES_PASSWORD": "p"}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("POSTGRES_SSLMODE", raising=False)
    if sslmode:
        monkeypatch.setenv("POSTGRES_SSLMODE", sslmode)
    monkeypatch.setattr(database, "load_dotenv", lambda *a, **k: None)
    seen = {}

    def fake_connect(**kwargs):
        seen.update(kwargs)
        raise database.psycopg.OperationalError("stop")
    monkeypatch.setattr(database.psycopg, "connect", fake_connect)
    return seen


@pytest.mark.parametrize("mode", ["disable", "allow", "prefer"])
def test_remote_postgres_rejects_weak_sslmode(monkeypatch, mode):
    base_env(monkeypatch, "db.example.org", mode)
    with pytest.raises(RuntimeError, match="require or stronger"):
        database.connect()


def test_remote_postgres_defaults_to_require(monkeypatch):
    seen = base_env(monkeypatch, "db.example.org")
    with pytest.raises(RuntimeError, match="Could not connect"):
        database.connect()
    assert seen["sslmode"] == "require"


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "/var/run/postgresql"])
def test_local_postgres_keeps_prefer(monkeypatch, host):
    seen = base_env(monkeypatch, host)
    with pytest.raises(RuntimeError, match="Could not connect"):
        database.connect()
    assert seen["sslmode"] == "prefer"


def test_remote_ollama_needs_opt_in_and_tls(monkeypatch):
    monkeypatch.delenv("OLLAMA_ALLOW_REMOTE", raising=False)
    with pytest.raises(ValueError, match="OLLAMA_ALLOW_REMOTE"):
        ollama.OllamaClient("https://ollama.example.org")
    monkeypatch.setenv("OLLAMA_ALLOW_REMOTE", "1")
    with pytest.raises(ValueError, match="https"):
        ollama.OllamaClient("http://ollama.example.org")
    assert ollama.OllamaClient("https://ollama.example.org").base_url == "https://ollama.example.org"
    assert ollama.OllamaClient("http://localhost:11434")


def test_ollama_refuses_redirects(monkeypatch):
    client = ollama.OllamaClient("http://localhost:11434")
    seen = {}

    class Redirect:
        status_code = 302
        ok = True
        content = b""

    def post(url, **kwargs):
        seen.update(kwargs)
        return Redirect()
    monkeypatch.setattr(client.session, "post", post)
    with pytest.raises(ollama.OllamaError, match="redirecionamento"):
        client._request("/api/chat", {"model": "m"}, "OLLAMA_CHAT_TIMEOUT")
    assert seen["allow_redirects"] is False


def test_ollama_queue_wait_is_bounded(monkeypatch):
    client = ollama.OllamaClient("http://localhost:11434")
    client._semaphore = threading.BoundedSemaphore(1)
    client._semaphore.acquire()           # outra sessão ocupando a inferência
    monkeypatch.setenv("OLLAMA_QUEUE_TIMEOUT", "0.05")
    with pytest.raises(ollama.OllamaError, match="ocupado"):
        client._request("/api/chat", {"model": "m"}, "OLLAMA_CHAT_TIMEOUT")


def test_semaphore_is_released_after_a_connection_error(monkeypatch):
    client = ollama.OllamaClient("http://localhost:11434")
    client._semaphore = threading.BoundedSemaphore(1)

    def boom(*a, **k):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(client.session, "post", boom)
    with pytest.raises(ollama.OllamaError):
        client._request("/api/chat", {"model": "m"}, "OLLAMA_CHAT_TIMEOUT")
    assert client._semaphore.acquire(timeout=0.1)   # liberado


def test_streamlit_binds_to_loopback_only():
    import tomllib
    from pathlib import Path
    config = tomllib.loads((Path(__file__).parents[2] / ".streamlit" / "config.toml").read_text("utf-8"))
    assert config["server"]["address"] == "127.0.0.1"
