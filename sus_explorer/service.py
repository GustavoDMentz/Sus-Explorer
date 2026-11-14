from __future__ import annotations

import os
import re
import time
from uuid import uuid4

from .llm import OllamaAnalyst
from .rag import KnowledgeStore, answer_with_context, select_context_hits, needs_document_context
from .postgres_executor import PostgresQueryExecutor
from .query_history import record_query, safe_provenance, event, observe_result
from .schemas import DAILY_QUERY_UNSUPPORTED


_DAILY_INTENT = re.compile(
    r"\b(?:dia\s+\d{1,2}|por\s+dia|dia\s+a\s+dia|"
    r"(?:últimos?|primeiro|segundo|terceiro)\s+dias?|"
    r"todos?\s+os?\s+dias|diári[ao]s?|hoje|ontem|anteontem)\b|"
    r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b|"
    r"\b\d{4}-\d{2}-\d{2}\b|"
    r"\b\d{1,2}\s+de\s+"
    r"(?:janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro)\b",
    re.IGNORECASE,
)


FIELD_LABELS = {
    "year": "ano",
    "month": "mês",
    "day": "dia",
    "period": "período",
    "uf": "UF",
    "municipality": "município",
    "start_year": "ano inicial",
    "start_month": "mês inicial",
    "end_year": "ano final",
    "end_month": "mês final",
    "temporal_analysis": "ordem da diferença temporal",
}


def humanize_fields(fields: list[str]) -> list[str]:
    return [
        FIELD_LABELS.get(field, field)
        for field in fields
    ]


class SUSExplorer:
    def __init__(self, *, ollama_model=None):
        self.llm = OllamaAnalyst(model=ollama_model)
        self.knowledge = KnowledgeStore(self.llm.client)
        self.executor = PostgresQueryExecutor()
        self.pni = self.executor  # existing internal call sites use this attribute
        self.history_enabled = os.getenv("POSTGRES_HISTORY_ENABLED") == "1"
        self.version_history_enabled = os.getenv("ANALYTICAL_HISTORY_ENABLED") == "1"

    def _record_history(self, query_id, plan, result, status, duration_ms):
        if not getattr(self, "history_enabled", False):
            return "disabled"
        try:
            provenance = safe_provenance(result) if result is not None else {}
            source = (result.provenance.get("source_provenance", result.provenance)
                      if result is not None else {})
            executor = source.get("executor", "unknown") if result is not None else "unknown"
            record_query(query_id=query_id, plan=plan, executor=executor,
                         status=status, duration_ms=duration_ms,
                         provenance=provenance)
            return "saved"
        except Exception as exc:
            event("query_history_unavailable", level="WARNING",
                  error_type=type(exc).__name__)
            return "unavailable"

    def _observe_result(self, plan, result):
        if not getattr(self, 'version_history_enabled', False):
            return {"status": "disabled"}
        try:
            return {"status": "saved", **observe_result(plan=plan, result=result)}
        except Exception as exc:
            event("analytical_history_unavailable", level="WARNING",
                  error_type=type(exc).__name__)
            return {"status": "unavailable"}

    def ask(self, question: str) -> dict:
        # Validate before REGEX, Ollama or PostgreSQL access.
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question must be a non-empty string")
        if len(question.encode("utf-8")) > 4096:
            raise ValueError("Question exceeds the 4096-byte limit")
        if _DAILY_INTENT.search(question):
            return {
                "needs_clarification": True,
                "clarification_question": DAILY_QUERY_UNSUPPORTED,
                "missing": [],
                "missing_internal": [],
                "plan": {},
                "result": None,
                "answer": None,
            }
        plan = self.llm.plan(question)
        planner_source = getattr(self.llm, "last_planner_source", None)

        if plan.status == "needs_clarification":
            return {
                "needs_clarification": True,
                "clarification_question": (
                    plan.clarification_question
                    or "Preciso de mais informações para fazer a consulta."
                ),
                "missing": humanize_fields(plan.missing),
                "missing_internal": plan.missing,
                "plan": plan.model_dump(),
                "planner_source": planner_source,
                "result": None,
                "answer": None,
            }

        missing = self._missing_fields(plan)

        if missing:
            readable = humanize_fields(missing)

            if missing == ["year"]:
                question_text = "De qual ano?"
            elif missing == ["uf"]:
                question_text = "De qual estado (UF)?"
            else:
                question_text = (
                    "Preciso que você informe: "
                    + ", ".join(readable)
                    + "."
                )

            return {
                "needs_clarification": True,
                "clarification_question": question_text,
                "missing": readable,
                "missing_internal": missing,
                "plan": plan.model_dump(),
                "planner_source": planner_source,
                "result": None,
                "answer": None,
            }

        query_id = uuid4()
        started = time.perf_counter()
        result = None
        try:
            result = getattr(self, "executor", self.pni).execute(plan)
            version_history = self._observe_result(plan, result)
            rag_started = time.perf_counter()
            knowledge = getattr(self, "knowledge", None)
            document_context_requested = needs_document_context(question, plan.operation)
            hits = knowledge.search(question) if knowledge is not None and document_context_requested else []
            retrieval_ms = int((time.perf_counter() - rag_started) * 1000)
            context_hits = select_context_hits(hits)
            if document_context_requested:
                from .analytics.temporal_query import temporal_answer_payload
                payload = temporal_answer_payload(plan, result) if plan.operation == "temporal" else result.model_dump()
                answer = answer_with_context(self.llm.client, question, payload, context_hits)
            else:
                answer = self.llm.answer(question, plan, result)
            event("rag_answer_completed", retrieval_ms=retrieval_ms,
                  generation_ms=int((time.perf_counter() - rag_started) * 1000) - retrieval_ms,
                  retrieved_chunks=len(hits), included_chunks=len(context_hits))
        except Exception:
            self._record_history(query_id, plan, result, "FAILED",
                                 int((time.perf_counter() - started) * 1000))
            raise
        history_status = self._record_history(
            query_id, plan, result, "SUCCESS",
            int((time.perf_counter() - started) * 1000),
        )

        return {
            "needs_clarification": False,
            "clarification_question": None,
            "missing": [],
            "missing_internal": [],
            "plan": plan.model_dump(),
            "planner_source": planner_source,
            "result": result.model_dump(),
            "answer": answer,
            "sources": [{"documentId": h["document_id"], "citationId": f"{h['original_reference']}#chunk-{h['chunk_index']}", "title": h["title"],
                         "reference": h["original_reference"], "chunkIndex": h["chunk_index"],
                         "score": h["score"]} for h in context_hits],
            "query_id": str(query_id),
            "history_status": history_status,
            "version_history": version_history,
        }

    @staticmethod
    def _missing_fields(plan) -> list[str]:
        missing = []

        if not plan.uf:
            missing.append("uf")

        if plan.operation in {
            "count",
            "group",
            "latency",
        }:
            # Ano é obrigatório.
            #
            # Mês NÃO é obrigatório:
            # year=2024, month=None significa o ano inteiro.
            if plan.year is None:
                missing.append("year")

        elif plan.operation in {"timeseries", "temporal"}:
            required = {
                "start_year": plan.start_year,
                "start_month": plan.start_month,
                "end_year": plan.end_year,
                "end_month": plan.end_month,
            }

            for field, value in required.items():
                if value is None:
                    missing.append(field)

            if plan.operation == "temporal" and plan.temporal_analysis is None:
                missing.append("temporal_analysis")

        elif plan.operation is None:
            raise ValueError(
                "O planner não definiu uma operação."
            )

        return list(dict.fromkeys(missing))
