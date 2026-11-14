from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest
from sus_explorer.data_catalog import inspect_competencies


def fake_db(records):
    db = MagicMock()
    db.__enter__ = MagicMock(return_value=db)
    db.__exit__ = MagicMock(return_value=False)
    db.execute.return_value.fetchall.return_value = records
    return db


def test_catalog_reports_completed_partition_and_absence():
    db = fake_db([{"id": 7, "status": "SUCCESS", "records_received": 9,
                   "metadata": {"partition": "ano=2026/mes=05/uf=RS", "source_rows": 9},
                   "finished_at": datetime(2026, 5, 12, tzinfo=timezone.utc)}])
    result = inspect_competencies(uf="RS", year=2026, connect_db=lambda: db)
    assert len(result["rows"]) == 12
    assert result["rows"][4] == {"Mês": "05/2026", "Situação": "Disponível",
        "Registros": 9, "Execução": 7, "Última ingestão (UTC)": "2026-05-12T00:00:00+00:00"}
    assert result["rows"][0]["Situação"] == "Não encontrada"
    assert result["rows"][0]["Registros"] is None


def test_incomplete_partition_is_not_available():
    db = fake_db([{"id": 8, "status": "PARTIAL", "records_received": 8,
                   "metadata": {"partition": "ano=2026/mes=05/uf=RS", "source_rows": 9},
                   "finished_at": datetime(2026, 5, 12, tzinfo=timezone.utc)}])
    result = inspect_competencies(uf="RS", year=2026, connect_db=lambda: db)
    assert result["rows"][4]["Situação"] == "Incompleta"
    assert result["rows"][4]["Registros"] is None


@pytest.mark.parametrize("uf,year", [("R", 2026), ("rs", 2026), ("RS", 1999), ("RS", 2101)])
def test_catalog_rejects_invalid_parameters(uf, year):
    with pytest.raises(ValueError):
        inspect_competencies(uf=uf, year=year, connect_db=lambda: fake_db([]))
