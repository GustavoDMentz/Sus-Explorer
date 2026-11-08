"""Document indexing invariants without replacing the production path."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sus_explorer.rag import (INSUFFICIENT_CONTEXT, KnowledgeStore, chunks,
                              vector_literal, answer_with_context,
                              select_context_hits, needs_document_context)


def test_chunking_preserves_content_and_rejects_invalid_overlap():
    parts = list(chunks("Primeiro parágrafo.\n\nSegundo parágrafo.", 100, 10))
    assert "Primeiro parágrafo." in " ".join(parts)
    assert "Segundo parágrafo." in " ".join(parts)
    with pytest.raises(ValueError):
        list(chunks("texto", 100, 100))


def test_simple_count_does_not_require_vector_lookup():
    assert not needs_document_context("Quantas doses no AC em janeiro de 2020?", "count")
    assert needs_document_context("Explique a contagem no AC em janeiro de 2020", "count")
    assert needs_document_context("Qual a variação mensal?", "temporal")


def test_index_rejects_path_outside_trusted_root(tmp_path):
    root = tmp_path / "public"
    root.mkdir()
    outside = tmp_path / "private.md"
    outside.write_text("private")
    store = KnowledgeStore(Mock())
    with pytest.raises(ValueError, match="fora"):
        store.index(outside, root=root)


def test_vector_literal_is_numeric_only_after_client_validation():
    assert vector_literal([0.25, -0.5]) == "[0.25,-0.5]"


def test_context_is_bounded_and_documents_are_data(monkeypatch):
    monkeypatch.setenv("RAG_CONTEXT_CHARS", "200")
    client = Mock()
    client.chat.return_value = "Resposta"
    hits = [
        {"document_id": 1, "chunk_index": 0, "title": "Guia", "original_reference": "guia.md", "content": "Fato documentado."},
        {"document_id": 2, "chunk_index": 0, "title": "Longo", "original_reference": "longo.md", "content": "x" * 300},
    ]
    selected = select_context_hits(hits)
    assert len(selected) == 1
    answer = answer_with_context(client, "Pergunta", {"doses": 3}, selected)
    assert "guia.md#chunk-0" in answer
    assert "> Fato documentado." in answer
    assert "Resposta" not in answer
    client.chat.assert_not_called()
    assert "x" * 100 not in answer


def test_insufficient_or_unverifiable_context_never_falls_back_to_generation():
    client = Mock()
    assert answer_with_context(client, "O que significa?", {}, []) == INSUFFICIENT_CONTEXT
    invalid = [{"document_id": 1, "chunk_index": 0, "title": "Sem fonte",
                "original_reference": "", "content": "Afirmação sem origem."}]
    assert answer_with_context(client, "O que significa?", {}, invalid) == INSUFFICIENT_CONTEXT
    client.chat.assert_not_called()


def test_service_never_uses_free_generation_when_document_context_is_missing():
    from sus_explorer.query_result import QueryResult
    from sus_explorer.schemas import QueryPlan
    from sus_explorer.service import SUSExplorer

    explorer = SUSExplorer.__new__(SUSExplorer)
    explorer.llm = Mock()
    explorer.llm.plan.return_value = QueryPlan(operation="count", year=2020, month=1, uf="AC")
    explorer.executor = Mock()
    explorer.executor.execute.return_value = QueryResult(
        "count", {"doses": 3}, {"executor": "postgres"})
    explorer.knowledge = SimpleNamespace(search=Mock(return_value=[]))
    explorer.history_enabled = False
    explorer.version_history_enabled = False

    response = explorer.ask("Explique por que uma competência ausente não significa zero doses no AC em janeiro de 2020")
    assert response["answer"] == INSUFFICIENT_CONTEXT
    explorer.llm.answer.assert_not_called()
