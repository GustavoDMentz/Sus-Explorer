"""Regression checks for session-only Streamlit history."""
from pathlib import Path

from sus_explorer.session_history import append_session_history


def _payload(query_id):
    return {
        "query_id": query_id,
        "needs_clarification": False,
        "plan": {"operation": "count", "municipality_name": "private query text"},
        "result": {"data": {"doses": 3}, "provenance": {
            "executor": "r2", "period": "2026-05", "secret": "private token"
        }},
        "answer": "private model response",
    }


def test_history_records_only_current_session_metadata():
    session_a = append_session_history([], _payload("a"))
    session_b = append_session_history([], _payload("b"))
    assert [r["Consulta"] for r in session_a] == ["a"]
    assert [r["Consulta"] for r in session_b] == ["b"]
    assert "private" not in str(session_a)
    assert "doses" not in str(session_a)


def test_history_is_bounded_and_skips_clarifications():
    rows = []
    for i in range(30):
        rows = append_session_history(rows, _payload(str(i)))
    assert len(rows) == 20
    assert rows[0]["Consulta"] == "29"
    assert rows[-1]["Consulta"] == "10"
    assert append_session_history(rows, {"needs_clarification": True}) == rows


def test_public_streamlit_ui_does_not_fetch_shared_history():
    app = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert "recent_queries()" not in app
    assert "from sus_explorer.data.persistence.history import recent_queries" not in app
    assert "session_query_history" in app
