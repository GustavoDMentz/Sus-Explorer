"""Versioned allowlist of source columns stored in ``datasus_raw_records.payload``.

Only columns the product actually reads are kept. Everything else the official CSV
carries (patient pseudonyms, birth dates, postal codes, residence data, ...) is dropped
before it reaches the database, so a dump or backup cannot leak it.

How the list was built (version 1): every ``payload->>'<column>'`` read by
``postgres_executor`` (filters, groupings, latency, vaccine display), plus the
columns ``immunization_transform.project`` needs for the typed projection and the
record identity. A column is added only together with the code that reads it, in a new
version, and the version is recorded in each ingestion run's metadata.
"""
from __future__ import annotations

PAYLOAD_ALLOWLIST_VERSION = 1

_V1 = frozenset({
    # identity and typed projection (immunization_transform.project)
    "co_documento", "co_vacina", "dt_vacina",
    "co_municipio_estabelecimento", "sg_uf_estabelecimento",
    # filters and groupings (postgres_executor)
    "no_municipio_estabelecimento",
    "tp_sexo_paciente", "co_sexo",
    "nu_idade_paciente",
    "no_raca_cor_paciente", "co_raca_cor_paciente", "co_raca_cor",
    "ds_vacina", "sg_imunobiologico", "ds_nome",
    "ds_tipo_dose", "ds_dose_vacina", "co_dose_vacina", "co_dose",
    "co_cnes_estabelecimento", "co_cnes",
    "ds_sistema_origem", "co_sistema_origem",
    # latency
    "dt_entrada_rnds",
})

ALLOWLISTS = {1: _V1}


def allowed_columns(version: int = PAYLOAD_ALLOWLIST_VERSION) -> frozenset[str]:
    try:
        return ALLOWLISTS[version]
    except KeyError:
        raise ValueError(f"Unknown payload allowlist version: {version}") from None


def filter_row(row: dict, version: int = PAYLOAD_ALLOWLIST_VERSION) -> tuple[dict, list[str]]:
    """Return (kept columns, sorted names of dropped columns). Values are never inspected."""
    allowed = allowed_columns(version)
    kept = {name: value for name, value in row.items() if name in allowed}
    dropped = sorted(name for name in row if name not in allowed)
    return kept, dropped
