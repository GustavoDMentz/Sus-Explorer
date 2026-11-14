"""Local Ollama transport shared by planning, explanations and embeddings."""
from __future__ import annotations

import os
import threading
from functools import lru_cache
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter


class OllamaError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _inference_limit():
    count = int(os.getenv("OLLAMA_MAX_CONCURRENT", "1"))
    if not 1 <= count <= 16:
        raise ValueError("OLLAMA_MAX_CONCURRENT fora do intervalo")
    return threading.BoundedSemaphore(count)


class OllamaClient:
    def __init__(self, base_url: str | None = None):
        if os.getenv("AI_PROVIDER", "ollama").lower() != "ollama":
            raise ValueError("AI_PROVIDER deve ser ollama")
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/"):
            raise ValueError("OLLAMA_BASE_URL inválida")
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.mount(self.base_url, HTTPAdapter(pool_connections=4, pool_maxsize=4))
        self._semaphore = _inference_limit()

    def _request(self, path: str, payload: dict, timeout_name: str) -> dict:
        timeout = float(os.getenv(timeout_name, "120"))
        if timeout <= 0:
            raise ValueError(f"{timeout_name} deve ser positivo")
        with self._semaphore:
            try:
                response = self.session.post(self.base_url + path, json=payload, timeout=(5, timeout))
            except requests.Timeout:
                raise OllamaError("Ollama excedeu o tempo limite") from None
            except requests.ConnectionError:
                raise OllamaError("Ollama indisponível; verifique OLLAMA_BASE_URL") from None
        if response.status_code == 404:
            raise OllamaError(f"Modelo Ollama ausente: {payload['model']}. Execute ollama pull.")
        if not response.ok:
            raise OllamaError(f"Ollama retornou HTTP {response.status_code}")
        if len(response.content) > 2_000_000:
            raise OllamaError("Resposta Ollama excedeu o limite")
        try:
            return response.json()
        except ValueError:
            raise OllamaError("Resposta Ollama inválida") from None

    def chat(self, messages: list[dict], *, model: str | None = None, format=None, temperature: float = 0.2) -> str:
        model = model or os.getenv("OLLAMA_CHAT_MODEL", "qwen3:4b-instruct-2507-q4_K_M")
        payload = {"model": model, "messages": messages, "stream": False,
                   "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "0"),
                   "options": {"temperature": temperature, "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "4096"))}}
        if format is not None:
            payload["format"] = format
        result = self._request("/api/chat", payload, "OLLAMA_CHAT_TIMEOUT")
        content = result.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaError("Ollama retornou resposta vazia")
        return content

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:0.6b")
        result = self._request("/api/embed", {"model": model, "input": texts,
                        "truncate": False, "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "0")},
                        "OLLAMA_EMBED_TIMEOUT")
        vectors = result.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise OllamaError("Ollama retornou embeddings inválidos")
        expected = int(os.getenv("RAG_EMBEDDING_DIM", "1024"))
        if any(not isinstance(v, list) or len(v) != expected or
               any(not isinstance(x, (int, float)) or not -1e9 < x < 1e9 for x in v) for v in vectors):
            raise OllamaError(f"Dimensão ou valores de embedding incompatíveis; esperado {expected}")
        return vectors

    def model_digest(self, model: str) -> str:
        try:
            response = self.session.get(self.base_url + "/api/tags", timeout=(5, 10))
        except requests.RequestException:
            raise OllamaError("Ollama indisponível; verifique OLLAMA_BASE_URL") from None
        if not response.ok:
            raise OllamaError(f"Ollama retornou HTTP {response.status_code}")
        try:
            for item in response.json().get("models", []):
                if item.get("name") == model and isinstance(item.get("digest"), str):
                    return item["digest"]
        except ValueError:
            raise OllamaError("Lista de modelos Ollama inválida") from None
        raise OllamaError(f"Modelo Ollama ausente: {model}. Execute ollama pull.")
