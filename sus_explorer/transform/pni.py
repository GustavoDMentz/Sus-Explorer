"""
Transformações canônicas para agregação do SI-PNI.

Este módulo contém as regras de negócio que definem como o microdado
bruto do SI-PNI é normalizado e agregado para construção do cubo local.

Regras extraídas de build_cache.py SEM nenhuma alteração de comportamento.
"""

from __future__ import annotations

import pandas as pd


UFS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO",
    "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
    "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]

CUBE_ALIASES = {
    "municipality_code": [
        "co_municipio_estabelecimento",
        "co_municipio_ibge",
    ],
    "municipality_name": [
        "no_municipio_estabelecimento",
    ],
    "vaccine_code": ["co_vacina"],
    "sex": ["tp_sexo_paciente", "co_sexo"],
    "age": ["nu_idade_paciente"],
    "dose": [
        "ds_tipo_dose",
        "ds_dose_vacina",
        "co_dose_vacina",
        "co_dose",
    ],
}


def resolve_col(ds, logical_name: str) -> str | None:
    """Resolve um nome lógico para a coluna física presente no dataset."""
    names = set(ds.schema.names)
    for candidate in CUBE_ALIASES[logical_name]:
        if candidate in names:
            return candidate
    return None


def normalize_string(series: pd.Series) -> pd.Series:
    """Normalização canônica de strings do SI-PNI."""
    return (
        series.astype("string")
        .str.strip()
        .fillna("IGNORADO")
    )


def age_band_series(series: pd.Series) -> pd.Series:
    """Calcula a faixa etária a partir da idade numérica."""
    ages = pd.to_numeric(series, errors="coerce")

    return pd.cut(
        ages,
        bins=[-1, 4, 9, 14, 19, 29, 39, 49, 59, 69, 79, 200],
        labels=[
            "00-04", "05-09", "10-14", "15-19", "20-29",
            "30-39", "40-49", "50-59", "60-69", "70-79", "80+",
        ],
        include_lowest=True,
        right=True,
    ).astype("string").fillna("IGNORADA")


def partition_key(year: int, month: int, uf: str) -> str:
    """Chave canônica de partição no manifest."""
    return f"{year}/{uf}/{month:02d}"


def parse_ufs(raw: str | None) -> list[str]:
    """Parseia lista de UFs da CLI, validando contra UFS."""
    if not raw:
        return UFS.copy()

    values = [
        item.strip().upper()
        for item in raw.split(",")
        if item.strip()
    ]

    invalid = [
        uf for uf in values
        if uf not in UFS
    ]

    if invalid:
        raise ValueError(
            "UF inválida: " + ", ".join(invalid)
        )

    return values
