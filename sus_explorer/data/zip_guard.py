"""Defensive checks before streaming a CSV out of an official ZIP.

The ZIPs are read in streaming mode (never extracted to disk), so zip-slip does not
apply, but a hostile or corrupt archive could still exhaust CPU and time through a
huge declared size, an absurd compression ratio, thousands of members or ambiguous
duplicate names. The monthly OpenDataSUS files are about 1.4-4.3 GB compressed.
"""
from __future__ import annotations

import os
import zipfile

MAX_MEMBERS = 1000
MAX_COMPRESSION_RATIO = 200          # real monthly CSVs compress roughly 5-10x
DEFAULT_MAX_UNCOMPRESSED_BYTES = 200 * 1024**3


class UnsafeZipError(ValueError):
    """The archive violates a safety limit."""


def max_uncompressed_bytes() -> int:
    raw = os.getenv("SUS_ZIP_MAX_UNCOMPRESSED_BYTES")
    if raw is None:
        return DEFAULT_MAX_UNCOMPRESSED_BYTES
    try:
        value = int(raw)
    except ValueError:
        raise UnsafeZipError("SUS_ZIP_MAX_UNCOMPRESSED_BYTES deve ser inteiro") from None
    if value <= 0:
        raise UnsafeZipError("SUS_ZIP_MAX_UNCOMPRESSED_BYTES deve ser positivo")
    return value


def check_archive(archive: zipfile.ZipFile, member: str | None = None) -> None:
    """Raise UnsafeZipError when the archive, or the chosen member, is not safe to read."""
    infos = archive.infolist()
    if len(infos) > MAX_MEMBERS:
        raise UnsafeZipError(f"ZIP com mais de {MAX_MEMBERS} membros")
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise UnsafeZipError("ZIP com nomes de membro duplicados")
    for name in names:
        if name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/"):
            raise UnsafeZipError("ZIP com caminho de membro suspeito")
    if member is None:
        return
    info = archive.getinfo(member)
    if info.file_size > max_uncompressed_bytes():
        raise UnsafeZipError("Membro do ZIP excede o tamanho descompactado permitido")
    if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
        raise UnsafeZipError("Razão de compressão do membro do ZIP é suspeita")
