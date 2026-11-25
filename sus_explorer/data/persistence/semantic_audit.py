"""Read-only semantic integrity checks for the active SI-PNI snapshots."""
from __future__ import annotations

import json

from .database import connect_reader


LATEST_SUCCESS = """WITH latest AS (
  SELECT DISTINCT ON (metadata->>'partition') id, metadata
  FROM datasus_ingestion_runs
  WHERE resource_type='immunization' AND status='SUCCESS'
    AND jsonb_typeof(metadata->'source_rows')='number'
    AND (metadata->>'source_rows')::bigint=records_received
  ORDER BY metadata->>'partition', id DESC
)"""

CHECKS = (
    ("duplicate_event_in_snapshot", "ERROR", LATEST_SUCCESS + """
      SELECT count(*) AS n FROM (
        SELECT o.ingestion_run_id, o.raw_record_id
        FROM latest l JOIN datasus_raw_record_observations o ON o.ingestion_run_id=l.id
        GROUP BY o.ingestion_run_id, o.raw_record_id HAVING count(*) > 1
      ) duplicates"""),
    ("projection_revision_mismatch", "ERROR", LATEST_SUCCESS + """
      SELECT count(*) AS n
      FROM latest l JOIN datasus_raw_record_observations o ON o.ingestion_run_id=l.id
      JOIN datasus_raw_records r ON r.id=o.raw_record_id
      LEFT JOIN immunization_records i ON i.source_record_id=r.id
      WHERE i.source_record_id IS NULL OR i.source_revision<>o.revision OR r.revision<>o.revision"""),
    ("competence_date_mismatch", "ERROR", LATEST_SUCCESS + """
      SELECT count(*) AS n
      FROM latest l JOIN datasus_raw_record_observations o ON o.ingestion_run_id=l.id
      JOIN immunization_records i ON i.source_record_id=o.raw_record_id
      WHERE extract(year FROM i.application_date)::int<>
              substring(l.metadata->>'partition' from 5 for 4)::int
         OR extract(month FROM i.application_date)::int<>
              substring(l.metadata->>'partition' from 14 for 2)::int"""),
    ("uf_partition_mismatch", "ERROR", LATEST_SUCCESS + """
      SELECT count(*) AS n
      FROM latest l JOIN datasus_raw_record_observations o ON o.ingestion_run_id=l.id
      JOIN immunization_records i ON i.source_record_id=o.raw_record_id
      WHERE i.establishment_uf<>right(l.metadata->>'partition', 2)"""),
    ("invalid_municipality_code", "ERROR", LATEST_SUCCESS + """
      SELECT count(*) AS n
      FROM latest l JOIN datasus_raw_record_observations o ON o.ingestion_run_id=l.id
      JOIN immunization_records i ON i.source_record_id=o.raw_record_id
      WHERE i.establishment_municipality_code !~ '^[0-9]{6,7}$'"""),
    ("record_key_across_competences", "WARNING", LATEST_SUCCESS + """
      SELECT count(*) AS n FROM (
        SELECT r.record_key
        FROM latest l JOIN datasus_raw_record_observations o ON o.ingestion_run_id=l.id
        JOIN datasus_raw_records r ON r.id=o.raw_record_id
        GROUP BY r.record_key HAVING count(DISTINCT l.metadata->>'partition') > 1
      ) reused"""),
)


def audit(connection=None) -> dict:
    own = connection is None
    db = connection or connect_reader()
    try:
        results = []
        for name, severity, statement in CHECKS:
            row = db.execute(statement).fetchone()
            count = int(row["n"])
            results.append({"check": name, "severity": severity, "count": count,
                            "passed": count == 0})
        return {"scope": "SI-PNI vaccination event records",
                "metric": "doses/registros; not unique patients, visits, coverage or money",
                "checks": results,
                "errors": sum(not item["passed"] and item["severity"] == "ERROR"
                              for item in results),
                "warnings": sum(not item["passed"] and item["severity"] == "WARNING"
                                for item in results)}
    finally:
        if own:
            db.close()


def main() -> int:
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
