"""
API central para o manifest do cache SI-PNI.

Extraído de build_cache.py sem alteração de comportamento.
O manifest existente em cache/pni_cube/manifest.json é patrimônio
operacional — este módulo é backward-compatible com schema_version = 1.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq


def utc_now() -> str:
    """Timestamp UTC ISO-8601."""
    return datetime.now(timezone.utc).isoformat()


def load_manifest(path: Path) -> dict:
    """Carrega o manifest JSON. Se não existir, retorna um vazio."""
    if not path.exists():
        return {
            "schema_version": 1,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "partitions": {},
        }

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(
            f"Manifest inválido: {path}: {exc}"
        ) from exc


def save_manifest(path: Path, manifest: dict) -> None:
    """Salva o manifest com escrita atômica (os.replace)."""
    manifest["updated_at"] = utc_now()
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def validate_existing_cache(path: Path) -> dict:
    """Valida um arquivo de cubo existente e retorna métricas."""
    metadata = pq.read_metadata(path)
    table = pq.read_table(path, columns=["doses"])
    doses = int(
        table["doses"]
        .combine_chunks()
        .to_numpy()
        .sum()
    )

    return {
        "rows_cube": metadata.num_rows,
        "doses": doses,
        "bytes": path.stat().st_size,
    }


def cache_file(
    cache_root: Path,
    year: int,
    month: int,
    uf: str,
) -> Path:
    """Caminho do cubo local para uma partição."""
    return (
        cache_root
        / f"ano={year}"
        / f"uf={uf}"
        / f"mes={month:02d}"
        / "cube.parquet"
    )
