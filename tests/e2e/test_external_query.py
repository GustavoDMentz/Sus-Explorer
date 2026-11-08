"""Opt-in Streamlit canary using a preloaded disposable PostgreSQL database and Ollama."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


pytestmark = pytest.mark.skipif(
    os.getenv("SUS_EXPLORER_EXTERNAL_TEST") != "1",
    reason="Set SUS_EXPLORER_EXTERNAL_TEST=1 after loading a known PostgreSQL partition",
)
APP = str(Path(__file__).resolve().parents[2] / "app.py")


def test_real_ollama_postgres_streamlit_count(monkeypatch):
    if os.getenv("SUS_EXPLORER_TEST_DB") != "1" or not os.getenv("POSTGRES_DB", "").endswith("_test"):
        pytest.skip("A disposable PostgreSQL *_test database is required")
    required = ("SUS_EXPLORER_EXTERNAL_YEAR", "SUS_EXPLORER_EXTERNAL_MONTH",
                "SUS_EXPLORER_EXTERNAL_UF", "SUS_EXPLORER_EXTERNAL_COUNT")
    if missing := [name for name in required if not os.getenv(name)]:
        pytest.skip("Missing canary configuration: " + ", ".join(missing))
    year = int(os.environ["SUS_EXPLORER_EXTERNAL_YEAR"])
    month = int(os.environ["SUS_EXPLORER_EXTERNAL_MONTH"])
    uf = os.environ["SUS_EXPLORER_EXTERNAL_UF"]
    expected = int(os.environ["SUS_EXPLORER_EXTERNAL_COUNT"])
    assert 2020 <= year <= 2100 and 1 <= month <= 12 and len(uf) == 2 and expected >= 0
    monkeypatch.delenv("R2_ENDPOINT", raising=False)
    monkeypatch.delenv("R2_ACCESS_KEY", raising=False)
    monkeypatch.delenv("R2_SECRET_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    months = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
              "agosto", "setembro", "outubro", "novembro", "dezembro")
    question = f"Quantas doses foram aplicadas na UF {uf} em {months[month - 1]} de {year}?"
    app = AppTest.from_file(APP, default_timeout=240).run()
    assert not app.exception
    app.text_area(key="query_question").set_value(question)
    app.button(key="FormSubmitter:query_form-Explorar").click().run()
    assert not app.exception
    payload = app.session_state["query_result"]
    assert payload and not payload["needs_clarification"]
    assert payload["plan"]["operation"] == "count"
    assert (payload["plan"]["uf"], payload["plan"]["year"], payload["plan"]["month"]) == (uf, year, month)
    assert payload["result"]["data"]["doses"] == expected
    assert payload["result"]["provenance"]["executor"] == "postgres"
    assert payload["answer"]
