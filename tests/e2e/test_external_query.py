"""Explicitly authorized, bounded external canary: two R2 months, Gemini and PG.

Never runs on the default pytest/CI path. Requires an independently established
expected count and a disposable PostgreSQL database.
"""

import os
from fractions import Fraction
from pathlib import Path
from uuid import uuid4

import pytest
import streamlit as st
from dotenv import load_dotenv
from psycopg import sql
from streamlit.testing.v1 import AppTest

from sus_explorer.data.persistence.database import connect
from sus_explorer.data.persistence.history import recent_queries
from sus_explorer.data.persistence.migrate import migrate


load_dotenv()

pytestmark = pytest.mark.skipif(
    os.getenv("SUS_EXPLORER_EXTERNAL_TEST") != "1",
    reason="Explicit SUS_EXPLORER_EXTERNAL_TEST=1 required for paid external calls",
)
APP = str(Path(__file__).resolve().parents[2] / "app.py")


def test_real_gemini_r2_streamlit_temporal_and_disposable_history(monkeypatch):
    if os.getenv("SUS_EXPLORER_TEST_DB") != "1" or not os.getenv("POSTGRES_DB", "").endswith("_test"):
        pytest.skip("A disposable PostgreSQL *_test database is required")
    required = (
        "GEMINI_API_KEY", "R2_ENDPOINT", "R2_ACCESS_KEY", "R2_SECRET_KEY",
        "SUS_EXPLORER_EXTERNAL_YEAR", "SUS_EXPLORER_EXTERNAL_MONTH",
        "SUS_EXPLORER_EXTERNAL_UF", "SUS_EXPLORER_EXTERNAL_COUNT",
        "SUS_EXPLORER_EXTERNAL_PREVIOUS_COUNT",
    )
    if missing := [name for name in required if not os.getenv(name)]:
        pytest.skip("Missing external test configuration: " + ", ".join(missing))
    year = int(os.environ["SUS_EXPLORER_EXTERNAL_YEAR"])
    month = int(os.environ["SUS_EXPLORER_EXTERNAL_MONTH"])
    uf = os.environ["SUS_EXPLORER_EXTERNAL_UF"]
    expected = int(os.environ["SUS_EXPLORER_EXTERNAL_COUNT"])
    previous = int(os.environ["SUS_EXPLORER_EXTERNAL_PREVIOUS_COUNT"])
    assert 2020 <= year <= 2100 and 2 <= month <= 12 and uf in {
        "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
        "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
    }
    assert expected >= 0 and previous >= 0
    schema = "external_test_" + uuid4().hex
    with connect() as connection:
        migrate(connection, schema=schema)
    monkeypatch.setenv("POSTGRES_SCHEMA", schema)
    monkeypatch.setenv("POSTGRES_COUNT_ENABLED", "0")
    monkeypatch.setenv("POSTGRES_HISTORY_ENABLED", "1")
    st.cache_resource.clear()
    try:
        months = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
                  "agosto", "setembro", "outubro", "novembro", "dezembro")
        question = f"Quantas doses foram aplicadas na UF {uf} em {months[month - 1]} de {year}?"
        app = AppTest.from_file(APP).run()
        assert not app.exception
        # BYOK credentials must be submitted explicitly in the Streamlit session.
        app.text_input(key="byok_gemini").set_value(os.environ["GEMINI_API_KEY"])
        app.button(key="FormSubmitter:byok_credentials-Usar credenciais nesta sessão").click().run()
        assert not app.exception
        assert app.session_state.get("byok_explorer") is not None
        app.text_area(key="query_question").set_value(question)
        app.button(key="FormSubmitter:query_form-Explorar").click().run()
        assert not app.exception
        assert app.session_state.get("query_result") is not None, (
            "Query did not produce a result: " + str(app.session_state.get("query_error"))
        )
        payload = app.session_state["query_result"]
        assert not payload["needs_clarification"]
        assert payload["plan"]["operation"] == "count"
        assert (payload["plan"]["uf"], payload["plan"]["year"], payload["plan"]["month"]) == (uf, year, month)
        assert payload["result"]["data"]["doses"] == expected
        assert payload["history_status"] == "saved"
        assert payload["answer"]
        assert len(app.dataframe) == 0  # count uses a metric, not a table
        count_id = payload["query_id"]
        temporal_question = (
            f"Qual foi a variação mensal das doses na UF {uf} "
            f"de {months[month - 2]} a {months[month - 1]} de {year}?"
        )
        app.text_area(key="query_question").set_value(temporal_question)
        app.button(key="FormSubmitter:query_form-Explorar").click().run()
        assert not app.exception
        assert app.session_state.get("query_result") is not None, (
            "Temporal query did not produce a result: " + str(app.session_state.get("query_error"))
        )
        temporal = app.session_state["query_result"]
        assert not temporal["needs_clarification"]
        assert temporal["plan"]["operation"] == "temporal"
        assert temporal["plan"]["temporal_analysis"]["order"] == 1
        assert (temporal["plan"]["uf"], temporal["plan"]["start_month"],
                temporal["plan"]["end_month"]) == (uf, month - 1, month)
        observed = temporal["result"]["data"]["rows"]
        assert [row["value"] for row in observed] == [previous, expected]
        assert observed[1]["metrics"]["delta_1"]["value"] == expected - previous
        expected_pct = None if previous == 0 else str(Fraction(100 * (expected - previous), previous))
        assert observed[1]["metrics"]["pct_change"]["value"] == expected_pct
        assert temporal["history_status"] == "saved"
        assert len(app.dataframe) == 1
        with connect() as connection:
            rows = recent_queries(connection=connection)
        assert len(rows) == 2
        assert {row["id"].hex for row in rows} == {
            count_id.replace("-", ""), temporal["query_id"].replace("-", "")}
        assert {row["executor"] for row in rows} == {"r2"}
        assert {row["status"] for row in rows} == {"SUCCESS"}
    finally:
        st.cache_resource.clear()
        with connect() as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
