"""Validated SI-PNI analytics over completed PostgreSQL ingestion runs."""
from __future__ import annotations

import os
import time
import unicodedata

from .data.persistence.database import connect
from .query_result import QueryResult, months, require_ready_plan
from .schemas import QueryPlan
from .terminology import terminology


SOURCE_LABEL = "SI-PNI / PostgreSQL"
_GROUP_EXPRESSIONS = {
    "municipality": "r.payload->>'no_municipio_estabelecimento'",
    "sex": "coalesce(r.payload->>'tp_sexo_paciente', r.payload->>'co_sexo')",
    "age": "r.payload->>'nu_idade_paciente'",
    "dose": "coalesce(r.payload->>'ds_tipo_dose', r.payload->>'ds_dose_vacina', r.payload->>'co_dose_vacina', r.payload->>'co_dose')",
    "facility": "coalesce(r.payload->>'co_cnes_estabelecimento', r.payload->>'co_cnes')",
    "system_origin": "coalesce(r.payload->>'ds_sistema_origem', r.payload->>'co_sistema_origem')",
    "race": "coalesce(r.payload->>'no_raca_cor_paciente', r.payload->>'co_raca_cor_paciente', r.payload->>'co_raca_cor')",
}


def _ascii_upper(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return "".join(char for char in value if not unicodedata.combining(char)).upper().strip()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class PostgresQueryExecutor:
    def __init__(self, *, connect_db=connect):
        self.connect_db = connect_db

    def _periods(self, plan: QueryPlan) -> list[tuple[int, int]]:
        if plan.operation in ("timeseries", "temporal"):
            return list(months(plan.start_year, plan.start_month, plan.end_year, plan.end_month))
        if plan.year is None:
            raise ValueError("Ano obrigatório")
        return [(plan.year, plan.month)] if plan.month else [(plan.year, month) for month in range(1, 13)]

    def _ready(self, db, plan: QueryPlan):
        periods = self._periods(plan)
        labels = [f"ano={year}/mes={month:02d}/uf={plan.uf}" for year, month in periods]
        rows = db.execute("""SELECT DISTINCT ON (metadata->>'partition')
                 id, source, source_resource_id, status, records_received, metadata
            FROM datasus_ingestion_runs
            WHERE resource_type='immunization' AND metadata->>'partition'=ANY(%s)
            ORDER BY metadata->>'partition', id DESC""", (labels,)).fetchall()
        ready = {row["metadata"]["partition"]: row for row in rows
                 if row["status"] == "SUCCESS" and
                 type(row["metadata"].get("source_rows")) is int and
                 row["metadata"]["source_rows"] == row["records_received"] and
                 row["records_received"] >= 0}
        missing = [label for label in labels if label not in ready]
        selected = [ready[label] for label in labels if label in ready]
        if not selected:
            raise FileNotFoundError("Nenhuma partição PostgreSQL completa para o período solicitado.")
        return selected, missing

    def _filters(self, plan: QueryPlan, run_ids: list[int]):
        terms = ["run.id=ANY(%s)", "i.source_revision=r.revision"]
        values = [run_ids]
        if plan.municipality_code:
            terms.append("i.establishment_municipality_code=%s")
            values.append(plan.municipality_code)
        elif plan.municipality_name:
            terms.append("upper(r.payload->>'no_municipio_estabelecimento')=%s")
            values.append(_ascii_upper(plan.municipality_name))
        if plan.vaccine_code:
            terms.append("i.vaccine_code=%s")
            values.append(plan.vaccine_code)
        if plan.sex:
            terms.append("coalesce(r.payload->>'tp_sexo_paciente', r.payload->>'co_sexo')=%s")
            values.append(plan.sex)
        if plan.vaccine_text:
            codes = terminology.resolve_text(plan.vaccine_text)
            text = "upper(coalesce(r.payload->>'ds_vacina', r.payload->>'sg_imunobiologico', r.payload->>'ds_nome', ''))"
            terms.append(f"({text} LIKE %s ESCAPE '\\' OR i.vaccine_code=ANY(%s))")
            values.extend(["%" + _escape_like(_ascii_upper(plan.vaccine_text)) + "%", codes])
        if plan.age_min is not None or plan.age_max is not None:
            age = "CASE WHEN length(r.payload->>'nu_idade_paciente') <= 3 AND r.payload->>'nu_idade_paciente' ~ '^[0-9]+$' THEN (r.payload->>'nu_idade_paciente')::int END"
            if plan.age_min is not None:
                terms.append(f"{age} >= %s")
                values.append(plan.age_min)
            if plan.age_max is not None:
                terms.append(f"{age} <= %s")
                values.append(plan.age_max)
        return " AND ".join(terms), values

    @staticmethod
    def _from() -> str:
        return """FROM datasus_ingestion_runs run
            JOIN datasus_raw_records r ON r.source=run.source
              AND r.resource_type=run.resource_type
              AND r.source_resource_id=run.source_resource_id
            JOIN immunization_records i ON i.source_record_id=r.id"""

    def _provenance(self, plan, runs, missing, started):
        labels = [run["metadata"]["partition"] for run in runs]
        return {"source": SOURCE_LABEL, "executor": "postgres",
                "ingestion_sources": sorted({run["source"] for run in runs}),
                "ingestion_run_ids": [run["id"] for run in runs],
                "uf_partition": plan.uf, "period": f"{plan.year}-{plan.month:02d}" if plan.month else str(plan.year) if plan.year else None,
                "partition": labels[0] if len(labels) == 1 else None,
                "partitions": labels, "partitions_consulted": len(labels),
                "missing_partitions": missing,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "microdata_sent_to_llm": False}

    def execute(self, plan: QueryPlan) -> QueryResult:
        plan = require_ready_plan(plan)
        if plan.operation == "temporal":
            from .analytics.temporal_query import execute_temporal
            return execute_temporal(plan, self.execute)
        if plan.operation not in ("count", "group", "timeseries", "latency"):
            raise ValueError("Operação não suportada")
        started = time.perf_counter()
        with self.connect_db() as db:
            runs, missing = self._ready(db, plan)
            where, values = self._filters(plan, [run["id"] for run in runs])
            if plan.operation == "count":
                count = db.execute(f"SELECT count(*) AS n {self._from()} WHERE {where}", values).fetchone()["n"]
                data = {"doses": count}
            elif plan.operation == "timeseries":
                counts = db.execute(f"SELECT run.id, count(*) AS n {self._from()} WHERE {where} GROUP BY run.id", values).fetchall()
                by_run = {row["id"]: row["n"] for row in counts}
                data = {"rows": [{"period": f"{int(run['metadata']['partition'][4:8])}-{run['metadata']['partition'][13:15]}",
                                  "doses": by_run.get(run["id"], 0)} for run in runs]}
            elif plan.operation == "group":
                if plan.group_by == "vaccine":
                    expression = "i.vaccine_code"
                    displays = ", array_agg(DISTINCT coalesce(r.payload->>'ds_vacina', r.payload->>'sg_imunobiologico', r.payload->>'ds_nome')) AS displays"
                elif plan.group_by in _GROUP_EXPRESSIONS:
                    expression = _GROUP_EXPRESSIONS[plan.group_by]
                    displays = ""
                else:
                    raise ValueError("group_by inválido")
                total = db.execute(f"SELECT count(*) AS n {self._from()} WHERE {where}", values).fetchone()["n"]
                limit = min(plan.top_n, int(os.getenv("MAX_GROUP_ROWS", "50")))
                if not 1 <= limit <= 100:
                    raise ValueError("MAX_GROUP_ROWS inválido")
                grouped = db.execute(f"SELECT {expression} AS value, count(*) AS n{displays} {self._from()} WHERE {where} GROUP BY {expression} ORDER BY n DESC, value NULLS LAST LIMIT %s", (*values, limit)).fetchall()
                if plan.group_by == "vaccine":
                    rows = []
                    for row in grouped:
                        code = row["value"]
                        official = terminology.lookup(code) if code else None
                        variants = sorted({str(v).strip() for v in row["displays"] or [] if v and str(v).strip()})
                        rows.append({"code": code, "display": official.get("official_display") if official else variants[0] if variants else None,
                                     "official_display": official.get("official_display") if official else None,
                                     "definition": official.get("definition") if official else None,
                                     "definition_source": official.get("definition_source") if official else None,
                                     "terminology_conflict": bool(official.get("conflict")) if official else False,
                                     "source_displays": variants, "source_display_variants": len(variants), "count": row["n"]})
                else:
                    rows = [{"value": row["value"], "count": row["n"]} for row in grouped]
                data = {"group_by": plan.group_by, "rows": rows, "total_after_filters": total}
            else:
                # PostgreSQL 17 validates the source string before casting; bad dates
                # remain absent from latency statistics, as in the legacy calculation.
                db.execute("SET LOCAL TIME ZONE 'UTC'")
                query = f"""WITH valid AS (SELECT
                    CASE WHEN pg_input_is_valid(r.payload->>'dt_entrada_rnds', 'timestamp with time zone')
                      THEN EXTRACT(EPOCH FROM ((r.payload->>'dt_entrada_rnds')::timestamptz
                        - (i.application_date::timestamp AT TIME ZONE 'UTC'))) / 86400.0 END AS days
                    {self._from()} WHERE {where}
                      AND i.application_date IS NOT NULL)
                    SELECT count(*) AS n,
                      percentile_cont(0.5) WITHIN GROUP (ORDER BY days) AS median,
                      percentile_cont(0.9) WITHIN GROUP (ORDER BY days) AS p90,
                      percentile_cont(0.95) WITHIN GROUP (ORDER BY days) AS p95
                    FROM valid WHERE days >= 0"""
                row = db.execute(query, values).fetchone()
                data = {"n_valid": row["n"], "median_days": round(row["median"], 3) if row["median"] is not None else None,
                        "p90_days": round(row["p90"], 3) if row["p90"] is not None else None,
                        "p95_days": round(row["p95"], 3) if row["p95"] is not None else None}
        provenance = self._provenance(plan, runs, missing, started)
        if plan.operation == "group" and plan.group_by == "vaccine":
            provenance["terminology"] = terminology.metadata()
            provenance["vaccine_grouping"] = {"canonical_key": "co_vacina", "source_display_role": "audit_only", "source_display_variants_preserved": True}
        warnings = (["Algumas partições mensais não estavam disponíveis e foram ignoradas: " + ", ".join(missing)] if missing else [])
        if plan.operation == "latency":
            warnings.insert(0, "Latência de registro não mede qualidade clínica nem prova atraso operacional.")
        return QueryResult(plan.operation, data, provenance, warnings)
