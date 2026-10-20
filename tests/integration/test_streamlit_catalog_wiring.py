"""End-to-end Streamlit wiring for the public catalog, without Gemini or R2."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[2] / "app.py")


def test_catalog_renders_and_compares_without_gemini_or_postgres(monkeypatch):
    calls = []

    def inspect(_pni, *, uf, year):
        calls.append((uf, year))
        fragments = 2 if len(calls) == 1 else 3
        return {
            "uf": uf, "year": year, "checked_at": "2026-10-20T17:00:00+00:00",
            "rows": [{
                "Mês": f"{month:02d}/{year}",
                "Situação": "Disponível" if month == 5 else "Não encontrada",
                "Fragmentos": fragments if month == 5 else 0,
                "Tamanho (MiB)": float(fragments) if month == 5 else 0.0,
                "Última modificação (UTC)": "2026-10-19T00:00:00+00:00" if month == 5 else None,
            } for month in range(1, 13)],
        }

    monkeypatch.setattr("sus_explorer.data_catalog.inspect_competencies", inspect)
    monkeypatch.setattr("sus_explorer.pni.PNIRemote", lambda: object())
    monkeypatch.setenv("POSTGRES_HISTORY_ENABLED", "0")
    monkeypatch.setenv("ANALYTICAL_HISTORY_ENABLED", "0")

    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert "byok_explorer" not in app.session_state

    app.button(key="catalog_check").click().run()
    assert not app.exception
    assert calls == [("RS", 2026)]
    assert len(app.session_state["catalog_result"]["rows"]) == 12
    assert app.session_state["catalog_comparison"] is None

    app.button(key="catalog_check").click().run()
    assert not app.exception
    assert calls == [("RS", 2026), ("RS", 2026)]
    assert app.session_state["catalog_comparison"][4]["Comparação"] == "Quantidade de fragmentos alterada"
    assert len(app.dataframe) == 2
