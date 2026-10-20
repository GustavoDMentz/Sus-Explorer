"""Minimal per-session UI history; never query the shared PostgreSQL history."""
from __future__ import annotations

from datetime import datetime, timezone


def append_session_history(rows: list[dict], payload: dict, *, limit: int = 20) -> list[dict]:
    """Return a bounded copy containing only metadata from this session's result."""
    if payload.get("needs_clarification") or not payload.get("query_id"):
        return list(rows[:limit])
    plan = payload.get("plan") or {}
    result = payload.get("result") or {}
    source = (result.get("provenance") or {})
    source = source.get("source_provenance", source)
    entry = {
        "Data e hora": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "Consulta": str(payload["query_id"]),
        "Operação": plan.get("operation", "—"),
        "Executor": source.get("executor", "unknown"),
        "Período": source.get("period", "—"),
    }
    return [entry, *rows][:limit]
