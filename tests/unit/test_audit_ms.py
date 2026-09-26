"""
Testes unitários sintéticos para o auditor independente SI-PNI.

REGRAS:
- Nenhum teste acessa R2 real.
- Nenhum teste lê ZIP real.
- Toda a camada de I/O é substituída por DataFrames sintéticos.
- Todos os testes usam apenas os símbolos públicos do módulo audit_ms.
"""

from __future__ import annotations

import pandas as pd
import pytest

from sus_explorer.cli.audit_ms import (
    KEYS,
    UFS,
    age_band,
    compare_ms_vs_cube,
    is_exact_match,
    norm,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures sintéticas
# ─────────────────────────────────────────────────────────────────────────────

def make_row(
    uf="RS",
    municipality_code="431490",
    municipality_name="PORTO ALEGRE",
    vaccine_code="85",
    sex="M",
    age_band_val="30-39",
    dose="1ª Dose",
) -> dict:
    return {
        "uf": uf,
        "municipality_code": municipality_code,
        "municipality_name": municipality_name,
        "vaccine_code": vaccine_code,
        "sex": sex,
        "age_band": age_band_val,
        "dose": dose,
    }


def make_ms(rows: list[dict], doses: list[int]) -> pd.DataFrame:
    if rows:
        df = pd.DataFrame(rows)
    else:
        df = pd.DataFrame(columns=KEYS)
    df["ms_doses"] = doses if doses else pd.Series([], dtype="int64")
    return df


def make_cube(rows: list[dict], doses: list[int]) -> pd.DataFrame:
    if rows:
        df = pd.DataFrame(rows)
    else:
        df = pd.DataFrame(columns=KEYS)
    df["cube_doses"] = doses if doses else pd.Series([], dtype="int64")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 1. Comparação exata — EXACT_MATCH
# ─────────────────────────────────────────────────────────────────────────────

def test_exact_match():
    row = make_row()
    ms = make_ms([row], [100])
    cube = make_cube([row], [100])

    different, metrics = compare_ms_vs_cube(ms, cube)

    assert metrics["missing_from_bucket"] == 0
    assert metrics["extra_in_bucket"] == 0
    assert metrics["changed_keys"] == 0
    assert metrics["different_keys"] == 0
    assert metrics["absolute_dose_delta"] == 0
    assert metrics["net_dose_delta"] == 0
    assert len(different) == 0
    assert is_exact_match(metrics, ms, cube)


def test_exact_match_status_string():
    row = make_row()
    ms = make_ms([row], [50])
    cube = make_cube([row], [50])

    _, metrics = compare_ms_vs_cube(ms, cube)

    status = "EXACT_MATCH" if is_exact_match(metrics, ms, cube) else "MISMATCH"
    assert status == "EXACT_MATCH"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Chave ausente no R2 (missing_from_bucket)
# ─────────────────────────────────────────────────────────────────────────────

def test_missing_from_bucket():
    row = make_row()
    ms = make_ms([row], [100])
    cube = make_cube([], [])  # cubo vazio

    different, metrics = compare_ms_vs_cube(ms, cube)

    assert metrics["missing_from_bucket"] == 1
    assert metrics["extra_in_bucket"] == 0
    assert metrics["different_keys"] == 1
    assert not is_exact_match(metrics, ms, cube)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Chave extra no R2 (extra_in_bucket)
# ─────────────────────────────────────────────────────────────────────────────

def test_extra_in_bucket():
    row = make_row()
    ms = make_ms([], [])  # MS vazio
    cube = make_cube([row], [100])

    different, metrics = compare_ms_vs_cube(ms, cube)

    assert metrics["missing_from_bucket"] == 0
    assert metrics["extra_in_bucket"] == 1
    assert metrics["different_keys"] == 1
    assert not is_exact_match(metrics, ms, cube)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Mesma chave com doses diferentes
# ─────────────────────────────────────────────────────────────────────────────

def test_changed_key_doses():
    row = make_row()
    ms = make_ms([row], [100])
    cube = make_cube([row], [99])  # 1 dose a menos

    different, metrics = compare_ms_vs_cube(ms, cube)

    assert metrics["changed_keys"] == 1
    assert metrics["missing_from_bucket"] == 0
    assert metrics["extra_in_bucket"] == 0
    assert metrics["absolute_dose_delta"] == 1
    assert metrics["net_dose_delta"] == -1
    assert metrics["different_keys"] == 1
    assert not is_exact_match(metrics, ms, cube)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Delta líquido zero mas diferenças existentes → MISMATCH
# ─────────────────────────────────────────────────────────────────────────────

def test_net_delta_zero_but_differences_exist():
    """Dois registros com deltas opostos: net=0 mas changed_keys=2 → MISMATCH."""
    row_a = make_row(uf="RS", vaccine_code="85")
    row_b = make_row(uf="SP", vaccine_code="85")
    ms = make_ms([row_a, row_b], [100, 100])
    cube = make_cube([row_a, row_b], [110, 90])  # +10, -10 → net=0

    different, metrics = compare_ms_vs_cube(ms, cube)

    assert metrics["net_dose_delta"] == 0
    assert metrics["changed_keys"] == 2
    assert metrics["absolute_dose_delta"] == 20
    assert not is_exact_match(metrics, ms, cube)
    assert "MISMATCH" == ("EXACT_MATCH" if is_exact_match(metrics, ms, cube) else "MISMATCH")


# ─────────────────────────────────────────────────────────────────────────────
# 6. UF inválida é não particionável
# ─────────────────────────────────────────────────────────────────────────────

def test_invalid_uf_is_unpartitionable():
    """UF 'XX' e string vazia não estão em UFS."""
    assert "XX" not in UFS
    assert "" not in UFS
    assert "ZZ" not in UFS
    # Todas as 27 UFs válidas devem estar presentes
    assert "RS" in UFS
    assert "SP" in UFS
    assert len(UFS) == 27


# ─────────────────────────────────────────────────────────────────────────────
# 7. Reagrupamento defensivo elimina duplicação
# ─────────────────────────────────────────────────────────────────────────────

def test_regroup_defensivo_elimina_duplicatas():
    """
    Se o cubo tiver a mesma chave em dois registros (duplicação acidental),
    compare_ms_vs_cube não deve ser chamado antes do reagrupamento.
    Testa que o reagrupamento defensivo em read_r2_cube seria necessário.

    Aqui testamos via compare_ms_vs_cube com cubo já reagrupado.
    """
    row = make_row()
    ms = make_ms([row], [100])

    # Cubo com chave duplicada — simula o que aconteceria SEM reagrupar
    cube_dup = pd.DataFrame([{**row, "cube_doses": 60}, {**row, "cube_doses": 40}])
    # Reagrupa defensivamente
    cube_regrouped = (
        cube_dup.groupby(KEYS, dropna=False, observed=True, as_index=False)["cube_doses"]
        .sum()
    )

    assert len(cube_regrouped) == 1
    assert int(cube_regrouped["cube_doses"].iloc[0]) == 100

    different, metrics = compare_ms_vs_cube(ms, cube_regrouped)
    assert is_exact_match(metrics, ms, cube_regrouped)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Geração de MISMATCH (string explícita)
# ─────────────────────────────────────────────────────────────────────────────

def test_mismatch_status_string():
    row = make_row()
    ms = make_ms([row], [100])
    cube = make_cube([row], [200])  # diverge

    _, metrics = compare_ms_vs_cube(ms, cube)
    status = "EXACT_MATCH" if is_exact_match(metrics, ms, cube) else "MISMATCH"

    assert status == "MISMATCH"


# ─────────────────────────────────────────────────────────────────────────────
# 9. Transformações independentes (norm e age_band)
# ─────────────────────────────────────────────────────────────────────────────

def test_norm_independent():
    """norm() usa implementação local — verifica comportamento esperado."""
    s = pd.Series(["  RS  ", None, "SP"])
    result = norm(s)
    assert result.iloc[0] == "RS"
    assert result.iloc[1] == "IGNORADO"
    assert result.iloc[2] == "SP"


def test_age_band_independent():
    """age_band() usa implementação local — verifica intervalos."""
    s = pd.Series([0, 4, 5, 29, 80, 200, -1, None])
    result = age_band(s)
    assert result.iloc[0] == "00-04"
    assert result.iloc[1] == "00-04"
    assert result.iloc[2] == "05-09"
    assert result.iloc[3] == "20-29"
    assert result.iloc[4] == "80+"
    assert result.iloc[5] == "80+"
    assert result.iloc[6] == "00-04"   # -1 cai no bin [-1,4]
    assert result.iloc[7] == "IGNORADA"
