"""Curated local documentation indexing and permission scoped retrieval."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from psycopg.types.json import Jsonb

from .data.persistence.database import connect
from .ollama import OllamaClient


INSUFFICIENT_CONTEXT = "Não encontrei trechos documentais suficientes para responder a essa parte. O resultado analítico, quando disponível, está separado e foi calculado no PostgreSQL."


def needs_document_context(question: str, operation: str) -> bool:
    if operation == "temporal":
        return True
    return bool(re.search(r"\b(?:explique|explicar|interprete|interpretação|significa|significado|metodologia|definição|por que|contexto|fundamentação)\b", question, re.IGNORECASE))


def chunks(text: str, size: int, overlap: int):
    if size < 100 or overlap < 0 or overlap >= size:
        raise ValueError("Configuração de chunk inválida")
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
    current = ""
    for block in blocks:
        for part in (block[i:i + size] for i in range(0, len(block), size)):
            if current and len(current) + len(part) + 2 > size:
                yield current
                current = current[-overlap:] if overlap else ""
            current = (current + "\n\n" + part).strip() if current else part
    if current:
        yield current


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(value, ".9g") for value in vector) + "]"


class KnowledgeStore:
    def __init__(self, client: OllamaClient | None = None):
        self.client = client or OllamaClient()
        self.model = os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:0.6b")
    @property
    def identity(self) -> str:
        return self.model + "@" + self.client.model_digest(self.model)

    def index(self, path: Path, *, root: Path, source: str = "project_docs") -> str:
        path = path.resolve()
        root = root.resolve()
        if not path.is_relative_to(root) or path.suffix.lower() not in (".md", ".txt"):
            raise ValueError("Fonte documental fora do diretório autorizado")
        if path.stat().st_size > 2_000_000:
            raise ValueError("Documento excede 2 MB")
        raw = path.read_bytes()
        content = raw.decode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        reference = str(path.relative_to(root)).replace("\\", "/")
        identity = self.identity
        with connect() as db:
            with db.cursor() as cur:
                cur.execute("SELECT content_hash, embedding_model FROM knowledge_documents WHERE original_reference=%s", (reference,))
                existing = cur.fetchone()
                if existing and existing["content_hash"] == digest and existing["embedding_model"] == identity:
                    return "unchanged"
        parts = list(chunks(content, int(os.getenv("RAG_CHUNK_SIZE", "700")), int(os.getenv("RAG_CHUNK_OVERLAP", "100"))))
        if not parts:
            raise ValueError("Documento sem texto")
        vectors = []
        try:
            for i in range(0, len(parts), 8):
                vectors.extend(self.client.embed(parts[i:i + 8]))
        except Exception as exc:
            with connect() as db, db.cursor() as cur:
                cur.execute("""INSERT INTO knowledge_indexing_attempts
                    (original_reference, content_hash, status, error_type)
                    VALUES (%s,%s,'FAILED',%s)""",
                    (reference, digest, type(exc).__name__))
            raise
        # All embeddings are ready before replacing the last valid index, and
        # the replacement itself is one transaction.
        with connect() as db:
            with db.transaction():
                with db.cursor() as cur:
                    cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (reference,))
                    cur.execute("""INSERT INTO knowledge_documents
                        (title, source, source_type, original_reference, content_hash, embedding_model)
                        VALUES (%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (original_reference) DO UPDATE SET
                          title=EXCLUDED.title, source=EXCLUDED.source,
                          source_type=EXCLUDED.source_type, content_hash=EXCLUDED.content_hash,
                            embedding_model=EXCLUDED.embedding_model, indexing_status='READY',
                          error_summary=NULL, updated_at=clock_timestamp()
                        RETURNING id""", (path.stem, source, "markdown" if path.suffix.lower() == ".md" else "text", reference, digest, identity))
                    document_id = cur.fetchone()["id"]
                    cur.execute("DELETE FROM knowledge_chunks WHERE document_id=%s", (document_id,))
                    for i, (part, vector) in enumerate(zip(parts, vectors)):
                        cur.execute("""INSERT INTO knowledge_chunks
                            (document_id, chunk_index, content, embedding, token_count, embedding_model)
                            VALUES (%s,%s,%s,%s::vector,%s,%s)""",
                            (document_id, i, part, vector_literal(vector), max(1, len(part) // 4), identity))
                    cur.execute("""INSERT INTO knowledge_indexing_attempts
                        (original_reference, content_hash, status)
                        VALUES (%s,%s,'SUCCESS')""", (reference, digest))
        return "indexed"

    def search(self, question: str, *, source: str = "project_docs",
               source_type: str | None = None, metadata: dict | None = None) -> list[dict]:
        if source_type not in (None, "markdown", "text") or not isinstance(metadata or {}, dict):
            raise ValueError("Filtro documental inválido")
        identity = self.identity
        vector = self.client.embed([question])[0]
        top_k = int(os.getenv("RAG_TOP_K", "5"))
        threshold = float(os.getenv("RAG_MIN_SIMILARITY", "0.65"))
        if not 1 <= top_k <= 20 or not -1 <= threshold <= 1:
            raise ValueError("Configuração RAG inválida")
        with connect() as db, db.cursor() as cur:
            cur.execute("""SELECT d.id AS document_id, d.title, d.original_reference,
                       c.chunk_index, c.content, c.metadata,
                       1 - (c.embedding <=> %s::vector) AS score
                FROM knowledge_chunks c JOIN knowledge_documents d ON d.id=c.document_id
                WHERE d.source=%s AND (%s::text IS NULL OR d.source_type=%s) AND
                      d.metadata @> %s::jsonb AND d.indexing_status='READY' AND
                      d.embedding_model=%s AND c.embedding_model=%s AND
                      1 - (c.embedding <=> %s::vector) >= %s
                ORDER BY c.embedding <=> %s::vector LIMIT %s""",
                (vector_literal(vector), source, source_type, source_type, Jsonb(metadata or {}), identity, identity,
                 vector_literal(vector), threshold, vector_literal(vector), top_k))
            return cur.fetchall()


def context_entry(hit: dict) -> str:
    return f"[documento {hit['document_id']}, trecho {hit['chunk_index']}, {hit['title']}]\n{hit['content']}"


def select_context_hits(hits: list[dict]) -> list[dict]:
    budget = int(os.getenv("RAG_CONTEXT_CHARS", "3500"))
    if not 200 <= budget <= 12000:
        raise ValueError("RAG_CONTEXT_CHARS fora do intervalo")
    selected = []
    used = 0
    for hit in hits:
        length = len(context_entry(hit))
        if used + length > budget:
            break
        selected.append(hit)
        used += length
    return selected


def answer_with_context(client: OllamaClient | None, question: str,
                        result_payload: dict, hits: list[dict]) -> str:
    """Render retrieved evidence verbatim; never ask a generator to paraphrase it.

    Citation IDs resolve to the persisted source reference and chunk index. Since
    the response contains only source excerpts, unsupported model claims cannot
    enter this path. The numeric result remains in its separate API field.
    """
    del client, question, result_payload
    if not hits:
        return INSUFFICIENT_CONTEXT
    entries = []
    seen = set()
    for hit in hits:
        content = hit.get("content")
        reference = hit.get("original_reference")
        chunk_index = hit.get("chunk_index")
        title = hit.get("title")
        document_id = hit.get("document_id")
        if (not isinstance(content, str) or not content.strip() or
                not isinstance(reference, str) or not reference.strip() or
                type(chunk_index) is not int or chunk_index < 0 or
                not isinstance(title, str) or type(document_id) is not int):
            continue
        citation_id = f"{reference}#chunk-{chunk_index}"
        if citation_id in seen:
            continue
        seen.add(citation_id)
        entries.append(f"**{title}** — `{citation_id}`\n> {content.strip().replace(chr(10), chr(10) + '> ')}")
    if not entries:
        return INSUFFICIENT_CONTEXT
    return "Trechos documentais recuperados (transcrição literal; consulte as referências para verificar):\n\n" + "\n\n".join(entries)
