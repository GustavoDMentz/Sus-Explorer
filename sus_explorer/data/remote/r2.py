"""
Acesso ao R2/S3 para dados do SI-PNI (healthbr-data).

Extraído de build_cache.py sem alteração de comportamento.
Credenciais vêm de settings/.env via config.py.
"""

from __future__ import annotations

import pyarrow.dataset as pds
import pyarrow.fs as fs

from ...config import settings


def make_filesystem() -> fs.S3FileSystem:
    """Cria o filesystem S3 configurado para o R2."""
    if not all([
        settings.r2_endpoint,
        settings.r2_access_key,
        settings.r2_secret_key,
    ]):
        raise RuntimeError("Configuração R2 ausente no .env")

    return fs.S3FileSystem(
        endpoint_override=settings.r2_endpoint,
        access_key=settings.r2_access_key,
        secret_key=settings.r2_secret_key,
        region=settings.r2_region,
    )


def partition_path(year: int, month: int, uf: str) -> str:
    """Caminho remoto da partição no bucket R2."""
    return (
        f"{settings.r2_bucket}/{settings.r2_prefix}/"
        f"ano={year}/mes={month:02d}/uf={uf}/"
    )


def open_partition(filesystem: fs.S3FileSystem, year: int, month: int, uf: str):
    """Abre um dataset PyArrow a partir de uma partição remota.

    Levanta FileNotFoundError se a partição não existir.
    """
    return pds.dataset(
        partition_path(year, month, uf),
        filesystem=filesystem,
        format="parquet",
    )
