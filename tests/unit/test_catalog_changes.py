import pytest
from sus_explorer.catalog_changes import compare_snapshots


def snapshot(*, uf="RS", records=2, run=1, modified="2026-10-19T00:00:00+00:00", status="Disponível"):
    return {"uf": uf, "year": 2026, "rows": [{
        "Mês": "05/2026", "Situação": status, "Registros": records,
        "Execução": run, "Última ingestão (UTC)": modified,
    }]}


def test_no_change():
    assert compare_snapshots(snapshot(), snapshot())[0]["Comparação"] == "Sem alteração detectada"


def test_record_change():
    assert compare_snapshots(snapshot(), snapshot(records=3))[0]["Comparação"] == "Quantidade de registros alterada"


def test_run_change():
    assert compare_snapshots(snapshot(), snapshot(run=2))[0]["Comparação"] == "Execução de ingestão alterada"


def test_modification_change():
    assert compare_snapshots(snapshot(), snapshot(modified="2026-10-20T00:00:00+00:00"))[0]["Comparação"] == "Data de ingestão alterada"


def test_unverified_is_not_a_change():
    result = compare_snapshots(snapshot(), snapshot(status="Não verificada", records=None, run=None, modified=None))
    assert result[0]["Comparação"] == "Comparação indisponível"


def test_availability_change():
    assert compare_snapshots(snapshot(), snapshot(status="Não encontrada", records=None, run=None, modified=None))[0]["Comparação"] == "Disponibilidade alterada"


def test_different_uf_rejected():
    with pytest.raises(ValueError):
        compare_snapshots(snapshot(), snapshot(uf="SP"))
