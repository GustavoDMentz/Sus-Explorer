"""
Testes de regressão para as transformações canônicas do SI-PNI.

Estes testes congelam o comportamento ATUAL das funções de
normalize_string, age_band_series e partition_key.

NÃO corrija o comportamento aqui.  Se algum teste falhar após uma
refatoração, é sinal de regressão — não de teste errado.
"""

from __future__ import annotations

import pandas as pd
import pytest

# Importa da localização canônica nova.
from sus_explorer.transform.pni import (
    age_band_series,
    normalize_string,
    partition_key,
)

# Importa também da localização original para garantir backward compat.
from sus_explorer.build_cache import (
    age_band_series as bc_age_band_series,
    normalize_string as bc_normalize_string,
    partition_key as bc_partition_key,
)


# ──────────────────────────────────────────────────────────
# normalize_string
# ──────────────────────────────────────────────────────────

class TestNormalizeString:
    """Congela o comportamento de normalize_string()."""

    def test_strips_whitespace(self):
        s = pd.Series([" RS "])
        assert normalize_string(s).iloc[0] == "RS"

    def test_none_becomes_ignorado(self):
        s = pd.Series([None])
        assert normalize_string(s).iloc[0] == "IGNORADO"

    def test_plain_string_unchanged(self):
        s = pd.Series(["abc"])
        assert normalize_string(s).iloc[0] == "abc"

    def test_empty_string_stays_empty(self):
        """Comportamento atual: string vazia NÃO é substituída por IGNORADO."""
        s = pd.Series([""])
        assert normalize_string(s).iloc[0] == ""

    def test_multiple_spaces_stripped(self):
        s = pd.Series(["  HELLO WORLD  "])
        assert normalize_string(s).iloc[0] == "HELLO WORLD"

    def test_numeric_cast_to_string(self):
        s = pd.Series([42])
        assert normalize_string(s).iloc[0] == "42"

    def test_batch(self):
        """Verifica processamento de um lote completo."""
        s = pd.Series([" RS ", None, "abc", "", 42])
        result = normalize_string(s).tolist()
        assert result == ["RS", "IGNORADO", "abc", "", "42"]


# ──────────────────────────────────────────────────────────
# age_band_series
# ──────────────────────────────────────────────────────────

class TestAgeBandSeries:
    """Congela o comportamento de age_band_series()."""

    @pytest.mark.parametrize(
        "age,expected",
        [
            (0, "00-04"),
            (4, "00-04"),
            (5, "05-09"),
            (9, "05-09"),
            (10, "10-14"),
            (14, "10-14"),
            (15, "15-19"),
            (19, "15-19"),
            (20, "20-29"),
            (29, "20-29"),
            (30, "30-39"),
            (39, "30-39"),
            (49, "40-49"),
            (59, "50-59"),
            (69, "60-69"),
            (79, "70-79"),
            (80, "80+"),
            (200, "80+"),
        ],
        ids=lambda v: f"age_{v}" if isinstance(v, int) else str(v),
    )
    def test_valid_ages(self, age, expected):
        s = pd.Series([age])
        assert age_band_series(s).iloc[0] == expected

    def test_minus_one_is_00_04(self):
        """Comportamento atual: -1 cai em [-1,4] → 00-04 (include_lowest)."""
        s = pd.Series([-1])
        assert age_band_series(s).iloc[0] == "00-04"

    @pytest.mark.parametrize(
        "age",
        [-2, 201, 300],
        ids=lambda v: f"age_{v}",
    )
    def test_out_of_range_is_ignorada(self, age):
        s = pd.Series([age])
        assert age_band_series(s).iloc[0] == "IGNORADA"

    def test_none_is_ignorada(self):
        s = pd.Series([None])
        assert age_band_series(s).iloc[0] == "IGNORADA"

    def test_non_numeric_is_ignorada(self):
        s = pd.Series(["abc"])
        assert age_band_series(s).iloc[0] == "IGNORADA"

    def test_gt_200_is_ignorada(self):
        """age > 200 cai fora dos bins → IGNORADA."""
        s = pd.Series([201])
        assert age_band_series(s).iloc[0] == "IGNORADA"

    def test_batch_preserves_order(self):
        """Verifica que o batch inteiro preserva a ordem e os valores."""
        ages = [0, 4, 5, 9, 80, 200, -1, -2, None, "abc"]
        expected = [
            "00-04", "00-04", "05-09", "05-09",
            "80+", "80+", "00-04", "IGNORADA",
            "IGNORADA", "IGNORADA",
        ]
        s = pd.Series(ages)
        result = age_band_series(s).tolist()
        assert result == expected


# ──────────────────────────────────────────────────────────
# partition_key
# ──────────────────────────────────────────────────────────

class TestPartitionKey:
    """Congela o formato da chave de partição."""

    def test_basic(self):
        assert partition_key(2023, 10, "RS") == "2023/RS/10"

    def test_single_digit_month_padded(self):
        assert partition_key(2023, 1, "SP") == "2023/SP/01"

    def test_december(self):
        assert partition_key(2024, 12, "MG") == "2024/MG/12"


# ──────────────────────────────────────────────────────────
# Backward compatibility: build_cache re-exports
# ──────────────────────────────────────────────────────────

class TestBackwardCompat:
    """Garante que build_cache re-exporta as mesmas funções."""

    def test_normalize_string_same_function(self):
        assert normalize_string is bc_normalize_string

    def test_age_band_series_same_function(self):
        assert age_band_series is bc_age_band_series

    def test_partition_key_same_function(self):
        assert partition_key is bc_partition_key
