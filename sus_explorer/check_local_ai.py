"""Verify required Ollama models and embedding dimension before migration."""
from __future__ import annotations

import os
import requests

from .ollama import OllamaClient, OllamaError


def main():
    client = OllamaClient()
    try:
        models = client.session.get(client.base_url + "/api/tags", timeout=(5, 10))
    except requests.RequestException:
        raise OllamaError("Ollama indisponível; verifique OLLAMA_BASE_URL") from None
    models.raise_for_status()
    available = {item["name"] for item in models.json().get("models", [])}
    required = {os.getenv("OLLAMA_CHAT_MODEL", "qwen3:4b-instruct-2507-q4_K_M"),
                os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:0.6b")}
    missing = required - available
    if missing:
        raise OllamaError("Modelos ausentes: " + ", ".join(sorted(missing)))
    vector = client.embed(["Validação local de dimensão do embedding."])[0]
    print(f"Ollama ready; models={', '.join(sorted(required))}; embedding_dimension={len(vector)}")


if __name__ == "__main__":
    main()
