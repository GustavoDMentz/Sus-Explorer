import pytest

from sus_explorer.catalog_changes import compare_snapshots


def snapshot(*, uf="RS", fragments=2, size=3.0, modified="2026-10-19T00:00:00+00:00", status="Disponível"):
    return {"uf": uf, "year": 2026, "rows": [{
        "Mês": "05/2026", "Situação": status, "Fragmentos": fragments,
        "Tamanho (MiB)": size, "Última modificação (UTC)": modified,
    }]}


def test_no_change():
    assert compare_snapshots(snapshot(), snapshot())[0]["Comparação"] == "Sem alteração detectada"


def test_fragment_change():
    assert compare_snapshots(snapshot(), snapshot(fragments=3))[0]["Comparação"] == "Quantidade de fragmentos alterada"


def test_size_change():
    assert compare_snapshots(snapshot(), snapshot(size=4.0))[0]["Comparação"] == "Tamanho alterado"


def test_modification_change():
    assert compare_snapshots(snapshot(), snapshot(modified="2026-10-20T00:00:00+00:00"))[0]["Comparação"] == "Data de modificação alterada"


def test_unverified_is_not_a_change():
    result = compare_snapshots(snapshot(), snapshot(status="Não verificada", fragments=None, size=None, modified=None))
    assert result[0]["Comparação"] == "Comparação indisponível"


def test_availability_change():
    assert compare_snapshots(snapshot(), snapshot(status="Não encontrada", fragments=0, size=0.0, modified=None))[0]["Comparação"] == "Disponibilidade alterada"


def test_different_uf_rejected():
    with pytest.raises(ValueError):
        compare_snapshots(snapshot(), snapshot(uf="SP"))
