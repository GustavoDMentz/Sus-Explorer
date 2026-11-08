"""Opt-in real Ollama embeddings + disposable PostgreSQL/pgvector evidence response."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from psycopg import sql

from sus_explorer.data.persistence.database import connect
from sus_explorer.data.persistence.migrate import migrate
from sus_explorer.ollama import OllamaClient
from sus_explorer.rag import KnowledgeStore, answer_with_context, select_context_hits


pytestmark = pytest.mark.skipif(
    os.getenv("SUS_EXPLORER_RAG_E2E") != "1",
    reason="Set SUS_EXPLORER_RAG_E2E=1 with local models and a disposable *_test database",
)


def test_real_index_search_and_generation(tmp_path, monkeypatch):
    if os.getenv("SUS_EXPLORER_TEST_DB") != "1" or not os.getenv("POSTGRES_DB", "").endswith("_test"):
        pytest.skip("Disposable PostgreSQL *_test database required")
    schema = "rag_test_" + uuid4().hex
    with connect() as db:
        migrate(db, schema=schema)
    monkeypatch.setenv("POSTGRES_SCHEMA", schema)
    monkeypatch.setenv("RAG_MIN_SIMILARITY", "-1")
    document = tmp_path / "guia.md"
    document.write_text("A análise mensal usa doses registradas, não pessoas vacinadas.\n\nUma partição ausente não equivale a zero doses.", encoding="utf-8")
    client = OllamaClient()
    store = KnowledgeStore(client)
    try:
        assert store.index(document, root=tmp_path) == "indexed"
        assert store.index(document, root=tmp_path) == "unchanged"
        hits = store.search("O que significa uma partição ausente?")
        assert hits and hits[0]["original_reference"] == "guia.md"
        selected = select_context_hits(hits)
        answer = answer_with_context(client, "O que significa uma partição ausente?", {}, selected)
        assert "guia.md#chunk-" in answer
        assert "Uma partição ausente não equivale a zero doses." in answer
    finally:
        with connect() as db:
            db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
