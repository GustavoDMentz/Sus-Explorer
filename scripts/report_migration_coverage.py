"""Reconcile an R2 inventory manifest with PostgreSQL ingestion runs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sus_explorer.data.persistence.database import connect


def build_report(manifest: Path, resource_manifest: Path | None = None) -> dict:
    inventory = json.loads(manifest.read_text(encoding="utf-8"))
    partitions = inventory.get("partitions")
    if not isinstance(partitions, list):
        raise ValueError("Manifesto não contém lista de partições")
    resources = {}
    if resource_manifest is not None:
        source_inventory = json.loads(resource_manifest.read_text(encoding="utf-8"))
        resources = {(row["year"], row["month"]): row
                     for row in source_inventory.get("monthly_resources", [])}
    with connect() as db:
        db_identity = db.execute("SELECT current_database() AS database, current_schema() AS schema").fetchone()
        runs = db.execute("""SELECT DISTINCT ON (metadata->>'partition')
                id, metadata->>'partition' AS partition, status,
                records_received, records_inserted, records_updated,
                metadata->>'source_sha256' AS source_sha256,
                metadata->>'source_rows' AS source_rows, error_summary,
                source, finished_at
            FROM datasus_ingestion_runs
            WHERE resource_type='immunization' AND metadata ? 'partition'
            ORDER BY metadata->>'partition', id DESC""").fetchall()
    latest = {row["partition"]: row for row in runs}
    result = []
    is_disposable = db_identity["database"].endswith("_test")
    counts = {key: 0 for key in ("migrated", "validated_in_disposable_db",
                                 "partial_or_failed", "in_progress", "pending")}
    rows_total = 0
    for entry in partitions:
        label = entry["partition"]
        year, month = int(label[4:8]), int(label[13:15])
        official = resources.get((year, month))
        run = latest.get(label)
        if run is None:
            status = "PENDING"
            reason = ("ZIP mensal oficial respondeu HTTP 200, mas a UF ainda não foi contada nem importada."
                      if official and official.get("available") else
                      "Nenhuma execução de ingestão registrada no PostgreSQL.")
            counts["pending"] += 1
        elif (run["status"] == "SUCCESS" and run["source_rows"] is not None and
              int(run["source_rows"]) == run["records_received"]):
            status = "VALIDATED_IN_DISPOSABLE_DB" if is_disposable else "MIGRATED_SUCCESS"
            reason = None
            counts["validated_in_disposable_db" if is_disposable else "migrated"] += 1
            rows_total += run["records_received"]
        elif run["status"] == "RUNNING":
            status = "IN_PROGRESS"
            reason = "Execução sem estado terminal; pode ser retomada após verificar o operador."
            counts["in_progress"] += 1
        else:
            status = run["status"]
            reason = run["error_summary"] or "Contagem recebida difere da quantidade de origem ou execução incompleta."
            counts["partial_or_failed"] += 1
        result.append({
            "partition": label,
            "status": status,
            "source_rows": int(run["source_rows"]) if run and run["source_rows"] else None,
            "records_received": run["records_received"] if run else None,
            "records_inserted": run["records_inserted"] if run else None,
            "records_updated": run["records_updated"] if run else None,
            "ingestion_run_id": run["id"] if run else None,
            "ingestion_source": run["source"] if run else None,
            "source_sha256": run["source_sha256"] if run else None,
            "official_month_resource_available": official.get("available") if official else None,
            "official_month_url": official.get("url") if official else None,
            "finished_at": run["finished_at"].isoformat() if run and run["finished_at"] else None,
            "reason": reason,
        })
    return {
        "inventory_source": inventory.get("source"),
        "inventory_checked_at": inventory.get("checked_at"),
        "database": db_identity["database"],
        "schema": db_identity["schema"],
        "disposable_test_database": is_disposable,
        "generated_from": str(manifest),
        "summary": {"partitions_total": len(result), **counts,
                    "records_received_on_successful_runs": rows_total},
        "partitions": result,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--resources", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.manifest, args.resources)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
