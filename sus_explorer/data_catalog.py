"""Read-only availability checks for monthly healthbr-data partitions.

This is an on-demand live R2 check, not a historical inventory or a guarantee
that every record in a partition is valid.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pyarrow.fs as fs


def inspect_competencies(pni, *, uf: str, year: int) -> dict:
    """Return availability per month without reading vaccination microdata."""
    if not (isinstance(uf, str) and len(uf) == 2 and uf.isalpha() and uf.isupper()):
        raise ValueError("UF inválida.")
    if not (isinstance(year, int) and 2000 <= year <= 2100):
        raise ValueError("Ano inválido.")

    rows = []
    for month in range(1, 13):
        path = pni.path(year, month, uf)
        try:
            infos = pni.s3.get_file_info(fs.FileSelector(path, recursive=False, allow_not_found=True))
            fragments = sum(1 for info in infos if info.type == fs.FileType.File and info.path.endswith(".parquet"))
            status = "Disponível" if fragments else "Não encontrada"
            rows.append({"Mês": f"{month:02d}/{year}", "Situação": status, "Fragmentos": fragments})
        except Exception:
            # Network, permission and transient failures must never mean zero data.
            rows.append({"Mês": f"{month:02d}/{year}", "Situação": "Não verificada", "Fragmentos": None})
    return {
        "uf": uf,
        "year": year,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": rows,
    }
