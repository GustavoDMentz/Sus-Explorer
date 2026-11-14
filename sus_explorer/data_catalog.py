"""Read-only availability of completed PostgreSQL SI-PNI partitions."""
from __future__ import annotations

from datetime import datetime, timezone

from .data.persistence.database import connect


def inspect_competencies(*, uf: str, year: int, connect_db=connect) -> dict:
    if not (isinstance(uf, str) and len(uf) == 2 and uf.isalpha() and uf.isupper()):
        raise ValueError("UF inválida.")
    if not (isinstance(year, int) and 2000 <= year <= 2100):
        raise ValueError("Ano inválido.")
    labels = [f"ano={year}/mes={month:02d}/uf={uf}" for month in range(1, 13)]
    with connect_db() as db:
        records = db.execute("""SELECT DISTINCT ON (metadata->>'partition')
            id, status, records_received, finished_at, metadata
            FROM datasus_ingestion_runs
            WHERE resource_type='immunization' AND metadata->>'partition'=ANY(%s)
            ORDER BY metadata->>'partition', id DESC""", (labels,)).fetchall()
    by_label = {record["metadata"]["partition"]: record for record in records}
    rows = []
    for month, label in enumerate(labels, 1):
        record = by_label.get(label)
        complete = bool(record and record["status"] == "SUCCESS" and
                        type(record["metadata"].get("source_rows")) is int and
                        record["metadata"]["source_rows"] == record["records_received"])
        rows.append({"Mês": f"{month:02d}/{year}",
                     "Situação": "Disponível" if complete else "Incompleta" if record else "Não encontrada",
                     "Registros": record["records_received"] if complete else None,
                     "Execução": record["id"] if record else None,
                     "Última ingestão (UTC)": record["finished_at"].isoformat() if record and record["finished_at"] else None})
    return {"uf": uf, "year": year,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "rows": rows}
