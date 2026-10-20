from types import SimpleNamespace

import pyarrow.fs as fs
import pytest

from sus_explorer.data_catalog import inspect_competencies


class FakeFS:
    def __init__(self, *, fail_month=None):
        self.fail_month = fail_month

    def get_file_info(self, selector):
        month = int(selector.base_dir.split("mes=")[1][:2])
        if month == self.fail_month:
            raise OSError("temporary unavailable")
        if month == 5:
            return [
                SimpleNamespace(type=fs.FileType.File, path=selector.base_dir + "part-0.parquet"),
                SimpleNamespace(type=fs.FileType.File, path=selector.base_dir + "part-1.parquet"),
                SimpleNamespace(type=fs.FileType.File, path=selector.base_dir + "_SUCCESS"),
            ]
        return []


def fake_pni(*, fail_month=None):
    return SimpleNamespace(
        s3=FakeFS(fail_month=fail_month),
        path=lambda year, month, uf: f"bucket/sipni/microdados/ano={year}/mes={month:02d}/uf={uf}/",
    )


def test_catalog_reports_parquet_fragments_and_absence():
    result = inspect_competencies(fake_pni(), uf="RS", year=2026)
    assert len(result["rows"]) == 12
    assert result["rows"][4] == {"Mês": "05/2026", "Situação": "Disponível", "Fragmentos": 2}
    assert result["rows"][0] == {"Mês": "01/2026", "Situação": "Não encontrada", "Fragmentos": 0}


def test_catalog_does_not_turn_network_failure_into_absence():
    result = inspect_competencies(fake_pni(fail_month=6), uf="RS", year=2026)
    assert result["rows"][5] == {"Mês": "06/2026", "Situação": "Não verificada", "Fragmentos": None}


@pytest.mark.parametrize("uf,year", [("R", 2026), ("rs", 2026), ("RS", 1999), ("RS", 2101)])
def test_catalog_rejects_invalid_parameters(uf, year):
    with pytest.raises(ValueError):
        inspect_competencies(fake_pni(), uf=uf, year=year)
