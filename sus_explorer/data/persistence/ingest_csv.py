"""Streaming import of an explicitly identified OpenDataSUS SI-PNI CSV file."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .database import connect
from .immunization_transform import project
from .operational_events import event
from .repositories import IngestionRunRepository, OperationalPersistence


REQUIRED = {"co_documento", "co_vacina", "dt_vacina",
            "co_municipio_estabelecimento", "sg_uf_estabelecimento"}
UFS = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())


@contextmanager
def _open_reader(path: Path, *, encoding: str, delimiter: str,
                 zip_member: str | None = None):
    if zip_member is not None or zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            members = [item.filename for item in archive.infolist()
                       if not item.is_dir() and item.filename.lower().endswith(".csv")]
            if zip_member is None:
                if len(members) != 1:
                    raise ValueError("ZIP deve conter exatamente um CSV ou informar --member")
                zip_member = members[0]
            if zip_member not in members:
                raise ValueError("Membro CSV não encontrado no ZIP")
            with archive.open(zip_member) as binary, io.TextIOWrapper(
                    binary, encoding=encoding, newline="") as stream:
                yield csv.DictReader(stream, delimiter=delimiter)
        return
    if zip_member is not None:
        raise ValueError("--member só pode ser usado com arquivo ZIP")
    with path.open("r", encoding=encoding, newline="") as stream:
        yield csv.DictReader(stream, delimiter=delimiter)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _snapshot(path: Path, *, encoding: str, delimiter: str,
              zip_member: str | None = None, uf: str | None = None):
    digest = _hash_file(path)
    with _open_reader(path, encoding=encoding, delimiter=delimiter,
                      zip_member=zip_member) as reader:
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)) or REQUIRED - set(reader.fieldnames):
            raise ValueError("CSV sem colunas obrigatórias ou com cabeçalhos duplicados")
        if uf is not None and "sg_uf_estabelecimento" not in reader.fieldnames:
            raise ValueError("CSV sem a UF de estabelecimento para filtrar a partição")
        count = sum(1 for row in reader if uf is None or row.get("sg_uf_estabelecimento") == uf)
    if _hash_file(path) != digest:
        raise ValueError("Arquivo CSV/ZIP mudou durante a leitura de validação")
    return {"sha256": digest, "rows": count}


def _counts(db, run_id, source, resource_id):
    return db.execute("""SELECT
       (SELECT count(*) FROM datasus_raw_record_observations WHERE ingestion_run_id=%s) AS observed,
       (SELECT count(*) FROM datasus_raw_record_observations o JOIN datasus_raw_records r ON r.id=o.raw_record_id
         WHERE o.ingestion_run_id=%s AND r.first_ingestion_run_id=%s) AS inserted,
       (SELECT count(*) FROM datasus_raw_record_observations o JOIN datasus_raw_records r ON r.id=o.raw_record_id
         WHERE o.ingestion_run_id=%s AND r.last_change_run_id=%s AND r.first_ingestion_run_id<>%s) AS updated,
       (SELECT count(*) FROM datasus_raw_records WHERE source=%s AND resource_type='immunization' AND source_resource_id=%s) AS raw_count,
       (SELECT count(*) FROM datasus_raw_record_observations o
         JOIN datasus_raw_records r ON r.id=o.raw_record_id
         JOIN immunization_records i ON i.source_record_id=r.id
         WHERE o.ingestion_run_id=%s AND o.revision=r.revision AND i.source_revision=r.revision) AS projected
       """, (run_id, run_id, run_id, run_id, run_id, run_id, source, resource_id, run_id)).fetchone()


def ingest_csv(path: Path, *, year: int, month: int, uf: str, resource_id: str,
               encoding: str = "utf-8-sig", delimiter: str = ",", batch_size: int = 1000,
               connection=None, zip_member: str | None = None) -> dict:
    if type(year) is not int or not 2020 <= year <= 2100 or type(month) is not int or not 1 <= month <= 12 or uf not in UFS:
        raise ValueError("Partição inválida")
    if not resource_id or len(resource_id) > 300 or any(char.isspace() for char in resource_id):
        raise ValueError("Identificador oficial do recurso inválido")
    if encoding not in ("utf-8-sig", "latin-1") or delimiter not in (",", ";") or not 1 <= batch_size <= 10000:
        raise ValueError("Formato ou lote inválido")
    path = path.resolve(strict=True)
    source = "opendatasus-csv"
    resource = f"{resource_id}/ano={year}/mes={month:02d}/uf={uf}"
    partition = f"ano={year}/mes={month:02d}/uf={uf}"
    snapshot = _snapshot(path, encoding=encoding, delimiter=delimiter,
                         zip_member=zip_member, uf=uf)
    metadata = {"partition": partition, "source_sha256": snapshot["sha256"],
                "source_rows": snapshot["rows"], "identity_column": "co_documento",
                "schema_version": 2, "source_filename": path.name}
    own_connection = connection is None
    db = connection or connect()
    run_id = None
    locked = False
    try:
        locked = db.execute("SELECT pg_try_advisory_lock(91627135, hashtext(%s)) AS acquired", (resource,)).fetchone()["acquired"]
        if not locked:
            raise RuntimeError("Outra ingestão ocupa esta partição")
        latest = db.execute("""SELECT * FROM datasus_ingestion_runs
            WHERE source=%s AND resource_type='immunization' AND source_resource_id=%s
            ORDER BY id DESC LIMIT 1""", (source, resource)).fetchone()
        if latest and latest["status"] == "SUCCESS" and latest["metadata"] == metadata:
            return latest
        if latest and latest["status"] == "RUNNING":
            if latest["metadata"] != metadata:
                raise RuntimeError("Há uma execução interrompida para outro snapshot; verifique-a antes de iniciar nova origem")
            run = latest  # replay from row one; record and observation keys make it idempotent
        else:
            runs = IngestionRunRepository(db)
            run = runs.start(source=source, resource_type="immunization", source_resource_id=resource, metadata=metadata)
        run_id = run["id"]
        db.commit()
        persisted = OperationalPersistence(db)
        seen = 0
        fetched_at = datetime.now(timezone.utc)
        with _open_reader(path, encoding=encoding, delimiter=delimiter,
                          zip_member=zip_member) as reader:
            while True:
                batch = []
                while len(batch) < batch_size:
                    row = next(reader, None)
                    if row is None:
                        break
                    if row.get("sg_uf_estabelecimento") == uf:
                        batch.append(row)
                if not batch:
                    break
                with db.transaction():
                    for row in batch:
                        seen += 1
                        key, payload, projection = project(row, uf)
                        if projection.application_date.year != year or projection.application_date.month != month:
                            raise ValueError("Data de vacinação fora da competência selecionada")
                        persisted.save_immunization(
                            source=source, resource_type="immunization", source_resource_id=resource,
                            record_key=key, external_id=key, payload=payload, fetched_at=fetched_at,
                            ingestion_run_id=run_id, projection=projection)
                event("csv_ingestion_batch", ingestion_run_id=run_id, rows_seen=seen)
        if _hash_file(path) != snapshot["sha256"] or seen != snapshot["rows"]:
            raise ValueError("Arquivo CSV mudou durante a ingestão")
        counts = _counts(db, run_id, source, resource)
        if not (counts["observed"] == counts["raw_count"] == counts["projected"] == seen):
            raise ValueError("Contagens da importação não conferem")
        result = runs.finish(run_id, status="SUCCESS", records_received=seen,
                             records_inserted=counts["inserted"], records_updated=counts["updated"])
        db.commit()
        event("csv_ingestion_completed", ingestion_run_id=run_id, rows_seen=seen)
        return result
    except Exception as exc:
        db.rollback()
        if run_id is not None:
            try:
                counts = _counts(db, run_id, source, resource)
                runs.finish(run_id, status="FAILED", records_received=counts["observed"],
                            records_inserted=counts["inserted"], records_updated=counts["updated"],
                            error_summary="CSV ingestion failed: " + type(exc).__name__)
                db.commit()
            except Exception:
                db.rollback()
        event("csv_ingestion_failed", level="ERROR", ingestion_run_id=run_id, error_type=type(exc).__name__)
        raise
    finally:
        if locked:
            try:
                db.execute("SELECT pg_advisory_unlock(91627135, hashtext(%s))", (resource,))
                db.commit()
            except Exception:
                db.rollback()
        if own_connection:
            db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--uf", required=True)
    parser.add_argument("--resource-id", required=True, help="Identificador do recurso oficial OpenDataSUS")
    parser.add_argument("--member", help="Nome do CSV dentro de um ZIP (opcional se houver apenas um)")
    parser.add_argument("--encoding", choices=("utf-8-sig", "latin-1"))
    parser.add_argument("--delimiter", choices=(",", ";"))
    args = parser.parse_args()
    zipped = zipfile.is_zipfile(args.file)
    result = ingest_csv(args.file, year=args.year, month=args.month, uf=args.uf,
                        resource_id=args.resource_id,
                        encoding=args.encoding or ("latin-1" if zipped else "utf-8-sig"),
                        delimiter=args.delimiter or (";" if zipped else ","),
                        zip_member=args.member)
    print(json.dumps({"ingestion_run_id": result["id"], "status": result["status"],
                      "records_received": result["records_received"]}))


if __name__ == "__main__":
    main()
