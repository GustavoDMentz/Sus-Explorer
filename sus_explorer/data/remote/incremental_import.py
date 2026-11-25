"""Incremental OpenDataSUS download and one-competence-at-a-time import.

The official SI-PNI file is national and monthly. This module keeps at most one
monthly ZIP in staging, supports HTTP Range resumption, imports selected UFs
sequentially, and deletes only a ZIP created by this job after every selected
partition has been reconciled successfully.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .opendatasus_catalog import (DATA_HOST, DATA_PATH_PATTERN, USER_AGENT,
                                  _check_url, _default_open)
from ..persistence.ingest_csv import UFS, ingest_csv


_ETAG = re.compile(r'^W/"[^"]+"$|^"[^"]+"$')


@dataclass(frozen=True)
class DownloadedFile:
    path: Path
    sha256: str
    size: int
    created_by_job: bool


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    os.replace(temporary, path)


def download_competence(entry: dict, staging: Path, *, opener=None,
                        chunk_size: int = 1024 * 1024) -> DownloadedFile:
    """Download one catalog entry, resuming a matching ``.part`` file."""
    if not 64 * 1024 <= chunk_size <= 16 * 1024 * 1024:
        raise ValueError("chunk_size fora do intervalo")
    url = entry.get("url")
    expected = entry.get("content_length")
    etag = entry.get("etag")
    if not isinstance(url, str):
        raise ValueError("Competência sem URL oficial")
    _check_url(url, DATA_HOST, DATA_PATH_PATTERN)
    if type(expected) is not int or expected <= 0:
        raise ValueError("Competência sem tamanho oficial verificável")
    if etag is not None and (not isinstance(etag, str) or not _ETAG.fullmatch(etag)):
        raise ValueError("ETag oficial inválido")

    staging = staging.resolve()
    staging.mkdir(parents=True, exist_ok=True)
    name = Path(urllib.parse.urlsplit(url).path).name
    final = staging / name
    partial = staging / (name + ".part")
    metadata_path = staging / (name + ".part.json")
    final_metadata_path = staging / (name + ".download.json")
    if final.exists():
        if final.stat().st_size != expected:
            raise ValueError("ZIP existente tem tamanho diferente do catálogo")
        digest = _sha256(final)
        final_metadata = (json.loads(final_metadata_path.read_text("utf-8"))
                          if final_metadata_path.exists() else None)
        owned = bool(final_metadata and final_metadata.get("identity") == {
            "url": url, "content_length": expected, "etag": etag
        } and final_metadata.get("sha256") == digest and final_metadata.get("created_by_job") is True)
        return DownloadedFile(final, digest, expected, owned)

    resume_at = partial.stat().st_size if partial.exists() else 0
    previous = json.loads(metadata_path.read_text("utf-8")) if metadata_path.exists() else None
    identity = {"url": url, "content_length": expected, "etag": etag}
    if resume_at and previous != identity:
        raise ValueError("Download parcial pertence a outro snapshot; preserve ou remova manualmente")
    if resume_at > expected:
        raise ValueError("Download parcial maior que a origem")
    _write_json(metadata_path, identity)

    if resume_at == expected:
        digest = _sha256(partial)
        os.replace(partial, final)
        metadata_path.unlink(missing_ok=True)
        _write_json(final_metadata_path, {"identity": identity, "sha256": digest,
                                          "created_by_job": True})
        return DownloadedFile(final, digest, expected, True)

    headers = {"User-Agent": USER_AGENT}
    if resume_at:
        headers["Range"] = f"bytes={resume_at}-"
        if etag:
            headers["If-Range"] = etag
    request = urllib.request.Request(url, headers=headers)
    try:
        response = (opener or _default_open)(request, timeout=60)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("Falha no download da competência") from exc
    with response:
        status = getattr(response, "status", None)
        status = response.getcode() if status is None else status
        if resume_at and status != 206:
            raise RuntimeError("Origem não confirmou a retomada por Range")
        if not resume_at and status != 200:
            raise RuntimeError(f"Download respondeu HTTP {status}")
        response_etag = response.headers.get("ETag") if hasattr(response, "headers") else None
        if etag and response_etag and response_etag != etag:
            raise RuntimeError("ETag mudou durante o download")
        if resume_at and hasattr(response, "headers"):
            content_range = response.headers.get("Content-Range")
            if content_range and not content_range.startswith(f"bytes {resume_at}-"):
                raise RuntimeError("Content-Range incompatível com o arquivo parcial")
        mode = "ab" if resume_at else "wb"
        with partial.open(mode) as output:
            while block := response.read(chunk_size):
                output.write(block)

    actual = partial.stat().st_size
    if actual != expected:
        raise RuntimeError(f"Download incompleto: {actual} de {expected} bytes")
    os.replace(partial, final)
    metadata_path.unlink(missing_ok=True)
    digest = _sha256(final)
    _write_json(final_metadata_path, {"identity": identity, "sha256": digest,
                                      "created_by_job": True})
    return DownloadedFile(final, digest, actual, True)


def import_competence(entry: dict, staging: Path, *, ufs: list[str],
                      delete_after_success: bool = False, opener=None,
                      ingest=ingest_csv) -> dict:
    """Download once and import each UF, persisting a resumable job checkpoint."""
    if not ufs or len(set(ufs)) != len(ufs) or any(uf not in UFS for uf in ufs):
        raise ValueError("Lista de UFs inválida")
    year, month = entry.get("year"), entry.get("month")
    resource_id = entry.get("resource_id")
    if type(year) is not int or type(month) is not int or not isinstance(resource_id, str):
        raise ValueError("Metadados de competência incompletos")
    downloaded = download_competence(entry, staging, opener=opener)
    checkpoint_path = staging.resolve() / f"import-{year:04d}-{month:02d}.json"
    checkpoint = ({"year": year, "month": month, "source_sha256": downloaded.sha256,
                   "source_size": downloaded.size, "partitions": {}}
                  if not checkpoint_path.exists()
                  else json.loads(checkpoint_path.read_text("utf-8")))
    if (checkpoint.get("source_sha256"), checkpoint.get("source_size")) != (
            downloaded.sha256, downloaded.size):
        raise ValueError("Checkpoint pertence a outro snapshot da competência")

    for uf in ufs:
        if checkpoint["partitions"].get(uf, {}).get("status") == "SUCCESS":
            continue
        result = ingest(downloaded.path, year=year, month=month, uf=uf,
                        resource_id=resource_id, encoding="latin-1", delimiter=";")
        if result["status"] != "SUCCESS":
            raise RuntimeError(f"Ingestão de {uf} não terminou com SUCCESS")
        checkpoint["partitions"][uf] = {
            "status": "SUCCESS", "ingestion_run_id": result["id"],
            "records_received": result["records_received"],
        }
        _write_json(checkpoint_path, checkpoint)

    checkpoint["complete"] = all(
        checkpoint["partitions"].get(uf, {}).get("status") == "SUCCESS" for uf in ufs)
    _write_json(checkpoint_path, checkpoint)
    if delete_after_success and checkpoint["complete"] and downloaded.created_by_job:
        downloaded.path.unlink()
        downloaded.path.with_name(downloaded.path.name + ".download.json").unlink(missing_ok=True)
        checkpoint["staging_file_removed"] = True
        _write_json(checkpoint_path, checkpoint)
    return checkpoint


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--ufs", nargs="+", default=sorted(UFS))
    parser.add_argument("--delete-after-success", action="store_true")
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text("utf-8"))
    matches = [row for row in catalog.get("competences", [])
               if (row.get("year"), row.get("month")) == (args.year, args.month)]
    if len(matches) != 1:
        raise SystemExit("Competência ausente ou duplicada no catálogo")
    result = import_competence(matches[0], args.staging, ufs=args.ufs,
                               delete_after_success=args.delete_after_success)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
