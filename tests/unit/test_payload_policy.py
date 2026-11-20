import pytest

from sus_explorer.data.persistence import payload_policy
from sus_explorer.data.persistence.immunization_transform import project
from sus_explorer.data.persistence.payload_policy import (
    PAYLOAD_ALLOWLIST_VERSION, allowed_columns, filter_row)

BASE = {"co_documento": "doc-1", "co_vacina": "33", "dt_vacina": "2026-05-01",
        "co_municipio_estabelecimento": "4314902", "sg_uf_estabelecimento": "RS"}
EXTRA = {"co_paciente": "P-123", "nu_cep": "90010000", "dt_nascimento_paciente": "1950-01-01",
         "no_paciente": "FULANO", "co_municipio_paciente": "3550308", "unexpected": float("nan")}


def test_identifiers_and_unused_columns_never_reach_the_payload():
    key, payload, projection = project(BASE | EXTRA | {"nu_idade_paciente": "40"}, "RS")
    assert key == "doc-1"
    assert payload == BASE | {"nu_idade_paciente": "40"}
    for name in EXTRA:
        assert name not in payload
    assert projection.vaccine_code == "33"


def test_columns_read_by_the_executor_are_kept():
    row = BASE | {"tp_sexo_paciente": "F", "no_raca_cor_paciente": "PARDA", "co_cnes_estabelecimento": "123",
                  "no_municipio_estabelecimento": "PORTO ALEGRE", "ds_tipo_dose": "1a dose",
                  "dt_entrada_rnds": "2026-05-03", "sg_imunobiologico": "INFLUENZA"}
    _, payload, _ = project(row, "RS")
    assert payload == row


def test_filter_row_reports_dropped_names_without_values():
    kept, dropped = filter_row(BASE | {"co_paciente": "secret-id", "nu_cep": "9"})
    assert dropped == ["co_paciente", "nu_cep"]
    assert "secret-id" not in repr(dropped)
    assert "co_paciente" not in kept


def test_allowlist_covers_everything_the_executor_reads():
    import re
    from pathlib import Path
    source = (Path(payload_policy.__file__).parents[2] / "postgres_executor.py").read_text("utf-8")
    used = set(re.findall(r"payload->>'([a-z_]+)'", source))
    assert used, "esperava colunas lidas do payload"
    assert used <= allowed_columns(), sorted(used - allowed_columns())


def test_allowlist_contains_no_patient_identifier_columns():
    forbidden_tokens = {"cpf", "cns", "cep", "nascimento", "endereco", "telefone", "email", "mae", "pai"}
    for column in allowed_columns():
        assert not forbidden_tokens & set(column.split("_")), column
    # Patient-related columns are limited to the attributes the product reads.
    patient_attributes = {"tp_sexo_paciente", "nu_idade_paciente", "no_raca_cor_paciente", "co_raca_cor_paciente"}
    assert {c for c in allowed_columns() if "paciente" in c} == patient_attributes


def test_unknown_version_is_rejected_and_current_version_is_one():
    assert PAYLOAD_ALLOWLIST_VERSION == 1
    with pytest.raises(ValueError):
        allowed_columns(99)
