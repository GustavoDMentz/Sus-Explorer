"""End-to-end Streamlit wiring for the public catalog, without Gemini or R2."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[2] / "app.py")


def test_catalog_renders_and_compares_postgres_status(monkeypatch):
    calls = []

    def inspect(*, uf, year):
        calls.append((uf, year))
        records = 2 if len(calls) == 1 else 3
        return {
            "uf": uf, "year": year, "checked_at": "2026-10-20T17:00:00+00:00",
            "rows": [{
                "Mês": f"{month:02d}/{year}",
                "Situação": "Disponível" if month == 5 else "Não encontrada",
                "Registros": records if month == 5 else None,
                "Execução": records if month == 5 else None,
                "Última ingestão (UTC)": "2026-10-19T00:00:00+00:00" if month == 5 else None,
            } for month in range(1, 13)],
        }

    monkeypatch.setattr("sus_explorer.data_catalog.inspect_competencies", inspect)
    monkeypatch.setenv("POSTGRES_HISTORY_ENABLED", "0")
    monkeypatch.setenv("ANALYTICAL_HISTORY_ENABLED", "0")

    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert "local_explorer" in app.session_state

    app.button(key="catalog_check").click().run()
    assert not app.exception
    assert calls == [("RS", 2026)]
    assert len(app.session_state["catalog_result"]["rows"]) == 12
    assert app.session_state["catalog_comparison"] is None

    app.button(key="catalog_check").click().run()
    assert not app.exception
    assert calls == [("RS", 2026), ("RS", 2026)]
    assert app.session_state["catalog_comparison"][4]["Comparação"] == "Quantidade de registros alterada"
    assert len(app.dataframe) == 2
