"""Real planner/parser, Parquet reader, analytics, service and Streamlit UI.

Only the paid Gemini transport and remote R2 filesystem are replaced. This is
local integration, not an external end-to-end test.
"""

from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import streamlit as st
from streamlit.testing.v1 import AppTest

from sus_explorer.llm import GeminiAnalyst
from sus_explorer.pni import PNIRemote
from sus_explorer.schemas import QueryPlan
from sus_explorer.service import SUSExplorer


APP = str(Path(__file__).resolve().parents[2] / "app.py")
QUESTION = "Qual foi a variação mensal das doses no RS de janeiro a abril de 2026?"


def test_local_parquet_through_planner_analytics_streamlit_and_rerun(tmp_path, monkeypatch):
    for month, count in ((1, 2), (2, 0), (4, 3)):
        partition = tmp_path / "ano=2026" / f"mes={month:02}" / "uf=RS"
        partition.mkdir(parents=True)
        table = pa.table({"record": list(range(count))}, schema=pa.schema([("record", pa.int64())]))
        pq.write_table(table, partition / "part.parquet")

    pni = PNIRemote.__new__(PNIRemote)
    pni.s3 = pa.fs.LocalFileSystem()
    pni.path = lambda year, month, uf: str(
        tmp_path / f"ano={year}" / f"mes={month:02}" / f"uf={uf}"
    )
    planner_response = {
        "operation": "temporal", "uf": "RS", "start_year": 2026,
        "start_month": 1, "end_year": 2026, "end_month": 4,
        "temporal_analysis": {"order": 1},
    }
    calls = []

    def generate_content(**kwargs):
        calls.append(kwargs)
        if "Explique em português claro" in str(kwargs.get("contents", "")):
            return SimpleNamespace(text="Resumo dos agregados.")
        return SimpleNamespace(parsed=planner_response, text=None, candidates=[])

    analyst = GeminiAnalyst.__new__(GeminiAnalyst)
    analyst.model = "test-model"
    analyst.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    monkeypatch.setattr("sus_explorer.service.GeminiAnalyst", lambda: analyst)
    monkeypatch.setattr("sus_explorer.service.PNIRemote", lambda: pni)
    monkeypatch.setenv("POSTGRES_HISTORY_ENABLED", "0")
    monkeypatch.setenv("POSTGRES_COUNT_ENABLED", "0")

    from sus_explorer.deterministic_planner import deterministic_plan
    import os
    fast_path = os.getenv("SUS_DETERMINISTIC_PLANNER") == "1" and deterministic_plan(QUESTION) is not None
    expected_calls = 1 if fast_path else 2

    service_result = SUSExplorer().ask(QUESTION)
    assert [row["value"] for row in service_result["result"]["data"]["rows"]] == [2, 0, None, 3]
    assert [row["metrics"]["delta_1"]["value"] for row in
            service_result["result"]["data"]["rows"]] == [None, -2, None, None]
    assert service_result["result"]["provenance"]["source_provenance"]["missing_partitions"] == [
        "ano=2026/mes=03/uf=RS"
    ]
    assert service_result["history_status"] == "disabled"

    calls.clear()
    st.cache_resource.clear()
    try:
        app = AppTest.from_file(APP).run()
        assert not app.exception
        app.text_area[0].set_value(QUESTION)
        app.button[0].click().run()
        assert not app.exception
        assert len(calls) == expected_calls
        assert app.session_state["query_result"]["result"]["data"] == service_result["result"]["data"]
        assert len(app.dataframe) == 1
        assert app.session_state["query_result"]["answer"] == "Resumo dos agregados."
        app.run()
        assert not app.exception
        assert len(calls) == expected_calls
    finally:
        st.cache_resource.clear()


def test_local_parquet_count_group_and_latency_use_actual_filters(tmp_path):
    partition = tmp_path / "ano=2026" / "mes=05" / "uf=RS"
    partition.mkdir(parents=True)
    rows = [
        {"tp_sexo_paciente": "F", "dt_vacina": "2026-05-01", "dt_entrada_rnds": "2026-05-02"},
        {"tp_sexo_paciente": "F", "dt_vacina": "2026-05-01", "dt_entrada_rnds": "2026-05-04"},
        {"tp_sexo_paciente": "M", "dt_vacina": "2026-05-04", "dt_entrada_rnds": "2026-05-03"},
        {"tp_sexo_paciente": "M", "dt_vacina": "2026-05-04", "dt_entrada_rnds": None},
    ]
    pq.write_table(pa.Table.from_pylist(rows), partition / "part.parquet")
    pni = PNIRemote.__new__(PNIRemote)
    pni.s3 = pa.fs.LocalFileSystem()
    pni.path = lambda year, month, uf: str(
        tmp_path / f"ano={year}" / f"mes={month:02}" / f"uf={uf}"
    )
    base = {"year": 2026, "month": 5, "uf": "RS"}
    assert pni.execute(QueryPlan(operation="count", **base)).data == {"doses": 4}
    assert pni.execute(QueryPlan(operation="count", sex="F", **base)).data == {"doses": 2}
    grouped = pni.execute(QueryPlan(operation="group", group_by="sex", **base))
    assert {row["value"]: row["count"] for row in grouped.data["rows"]} == {"F": 2, "M": 2}
    assert grouped.data["total_after_filters"] == 4
    latency = pni.execute(QueryPlan(operation="latency", **base))
    assert latency.data == {"n_valid": 2, "median_days": 2.0,
                            "p90_days": 2.8, "p95_days": 2.9}
