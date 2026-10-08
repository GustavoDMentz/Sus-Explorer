"""Explicit adapter from monthly QueryResult to deterministic temporal analytics."""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
import math
import os
import re

from ..operational_logging import redact
from ..config import settings
from ..schemas import QueryPlan
from .temporal import TemporalAnalytics, TemporalAnalyticsResult


FILTER_FIELDS = (
    "uf", "municipality_code", "municipality_name", "vaccine_code", "vaccine_text",
    "age_min", "age_max", "sex",
)
SOURCE_LABEL = "SI-PNI / healthbr-data / OpenDATASUS"


class TemporalQueryError(RuntimeError):
    """Controlled failure; never exposes a raw backend exception or payload."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _secrets() -> tuple[str, ...]:
    configured = vars(settings)
    return tuple(value for name, value in (list(os.environ.items()) + list(configured.items())) if isinstance(value, str) and value and
                 re.search(r"TOKEN|SECRET|PASSWORD|KEY|CREDENTIAL|DSN", name, re.I))


def safe_source_provenance(origin: dict) -> dict:
    """Keep the public timeseries contract only, dropping arbitrary nested metadata.

    Sanitization is an explicit projection; it does not change the private origin.
    Unknown source labels are not trusted as safe for external presentation.
    """
    if not isinstance(origin, dict):
        raise ValueError("Invalid source provenance")
    safe = {}
    if "source" in origin:
        safe["source"] = SOURCE_LABEL if origin["source"] == SOURCE_LABEL else "UNVERIFIED_SOURCE_LABEL"
    uf = origin.get("uf_partition")
    if isinstance(uf, str) and re.fullmatch(r"[A-Z]{2}", uf):
        safe["uf_partition"] = uf
    for key in ("partitions_consulted", "parquet_fragments"):
        if key in origin:
            value = origin[key]
            if type(value) is not int or value < 0:
                raise ValueError("Invalid source counters")
            safe[key] = value
    if "elapsed_seconds" in origin:
        value = origin["elapsed_seconds"]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("Invalid source elapsed time")
        safe["elapsed_seconds"] = value
    if "missing_partitions" in origin:
        values = origin["missing_partitions"]
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not re.fullmatch(
                r"ano=[0-9]{4}/mes=(0[1-9]|1[0-2])/uf=[A-Z]{2}", value
            ) for value in values
        ):
            raise ValueError("Invalid missing-partition metadata")
        safe["missing_partitions"] = list(values)
    if "vaccine_filter" in origin:
        value = origin["vaccine_filter"]
        if (not isinstance(value, dict) or value.get("method") != "source_text_or_authoritative_code_v1"
                or value.get("terminology_source") != "MS + SES-GO"
                or not isinstance(value.get("resolved_codes"), list)
                or any(not isinstance(code, str) or not re.fullmatch(r"[0-9]{1,8}", code)
                       for code in value["resolved_codes"])):
            raise ValueError("Invalid vaccine resolution metadata")
        safe["vaccine_filter"] = {key: value[key] for key in
            ("method", "terminology_source", "resolved_codes")}
        for key in ("ms_version", "ses_go_version"):
            if value.get(key) is None or isinstance(value.get(key), str) and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", value[key]):
                safe["vaccine_filter"][key] = value.get(key)
    if origin.get("microdata_sent_to_llm") is True:
        raise ValueError("Source violates aggregate-only contract")
    safe["microdata_sent_to_llm"] = False
    return redact(safe, _secrets())


def _reference(source_plan: dict, rows: list[dict]) -> str:
    canonical = json.dumps(
        {"query": source_plan, "rows": rows}, sort_keys=True,
        ensure_ascii=False, separators=(",", ":"), allow_nan=False,
        default=lambda value: str(value) if isinstance(value, Decimal) else None,
    )
    return "timeseries:sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _interpretation(order: int, value) -> str:
    if value is None:
        return "UNAVAILABLE"
    labels = {
        1: ("MONTHLY_VOLUME_DECREASING", "MONTHLY_VOLUME_UNCHANGED", "MONTHLY_VOLUME_INCREASING"),
        2: ("MONTHLY_CHANGE_DECREASING", "MONTHLY_CHANGE_UNCHANGED", "MONTHLY_CHANGE_INCREASING"),
        3: ("SECOND_DIFFERENCE_DECREASING", "SECOND_DIFFERENCE_UNCHANGED", "SECOND_DIFFERENCE_INCREASING"),
    }
    return labels[order][0 if value < 0 else 2 if value > 0 else 1]


def execute_temporal(plan: QueryPlan, execute_source) -> TemporalAnalyticsResult:
    # Revalidate even if a caller used model_copy/model_construct to bypass validation.
    plan = QueryPlan.model_validate(plan.model_dump())
    if plan.operation != "temporal" or plan.status != "ready":
        raise TemporalQueryError("INVALID_TEMPORAL_PLAN", "Plano temporal incompleto ou inválido.")
    origin_plan = QueryPlan.model_validate(
        plan.model_dump() | {"operation": "timeseries", "temporal_analysis": None}
    )
    source_query = {
        "operation": "timeseries", "granularity": "monthly",
        "start_year": plan.start_year, "start_month": plan.start_month,
        "end_year": plan.end_year, "end_month": plan.end_month,
        "filters": {key: getattr(plan, key) for key in FILTER_FIELDS},
    }
    source_query = redact(source_query, _secrets())
    try:
        origin = execute_source(origin_plan)
    except Exception:
        raise TemporalQueryError(
            "SOURCE_QUERY_FAILED", "Não foi possível consultar a série mensal de origem."
        ) from None
    try:
        if origin.operation != "timeseries" or not isinstance(origin.data, dict):
            raise ValueError("Invalid source operation/data")
        raw_rows = origin.data.get("rows")
        if not isinstance(raw_rows, list):
            raise ValueError("Monthly rows must be a list")
        rows = []
        for row in raw_rows:
            if not isinstance(row, dict) or "period" not in row or "doses" not in row:
                raise ValueError("Invalid monthly observation")
            # Never forward extra row fields (including accidental microdata).
            rows.append({"period": row["period"], "doses": row["doses"]})
        safe_origin = safe_source_provenance(origin.provenance)
        if safe_origin.get("uf_partition", plan.uf) != plan.uf:
            raise ValueError("Source UF does not match query")
        observed_periods = {row["period"] for row in rows}
        for partition in safe_origin.get("missing_partitions", []):
            year, month, uf = re.fullmatch(
                r"ano=([0-9]{4})/mes=([0-9]{2})/uf=([A-Z]{2})", partition
            ).groups()
            position = (int(year), int(month))
            if (uf != plan.uf or f"{year}-{month}" in observed_periods or
                not (plan.start_year, plan.start_month) <= position <= (plan.end_year, plan.end_month)):
                raise ValueError("Source absence metadata contradicts observations")
        # Calculate validates ordering, bounds, duplicates and exact numerical types.
        result = TemporalAnalytics.calculate(
            rows, start_period=f"{plan.start_year:04d}-{plan.start_month:02d}",
            end_period=f"{plan.end_year:04d}-{plan.end_month:02d}",
            source_series_ref="pending", source_provenance=safe_origin,
        )
        result.provenance["source_series_ref"] = _reference(source_query, rows)
    except (AttributeError, TypeError, ValueError, OverflowError):
        raise TemporalQueryError(
            "INVALID_SOURCE_SERIES", "A série mensal retornada não satisfaz o contrato temporal."
        ) from None
    order = plan.temporal_analysis.order
    key = f"delta_{order}"
    for row in result.data["rows"]:
        selected = row["metrics"][key]
        selected["interpretation"] = _interpretation(order, selected["value"])
        row["metrics"] = {key: selected}
        row["observation_classification"] = "DIRECT"
    result.operation = "temporal"
    result.provenance.update({
        "operation": "temporal", "order": order, "granularity": "monthly",
        "formula": result.provenance["formulas"][key],
        "source_classification": "DIRECT", "filters": source_query["filters"],
        "source_query": source_query,
        "metadata_policy": "public_timeseries_allowlist_and_secret_redaction_v1",
    })
    result.provenance["parameters"]["orders"] = [order]
    result.provenance["formulas"] = {key: result.provenance["formulas"][key]}
    result.provenance["units"] = {key: result.provenance["units"][key]}
    if any(row["observation_status"] != "OBSERVED" for row in result.data["rows"]):
        result.warnings.append("Meses ou valores indisponíveis: null, sem imputação nem diferenças atravessando lacunas.")
    from .percentage import add_percentages
    add_percentages(result)
    return result


def temporal_answer_payload(plan: QueryPlan, result) -> dict:
    """Validate/project the adapter's output at the external presentation boundary."""
    dumped = result.model_dump()
    if dumped["operation"] != "temporal" or dumped["provenance"].get("classification") != "DERIVED":
        raise TemporalQueryError("INVALID_TEMPORAL_RESULT", "Resultado temporal inválido.")
    # Only the adapter output is supported. Rebuild from the public structural keys.
    data = []
    key = f"delta_{plan.temporal_analysis.order}"
    for row in dumped["data"]["rows"]:
        metric = row["metrics"][key]
        data.append({
            name: row[name] for name in ("period", "value", "observation_status", "observation_classification")
        } | {"metrics": {key: {name: metric[name] for name in (
            "classification", "value", "unavailable_reasons", "interpretation"
        )}}})
    provenance_keys = (
        "operation", "classification", "order", "granularity", "formula", "formulas",
        "method", "method_version", "period", "parameters", "units", "unit_convention",
        "numeric_encoding", "source_series_ref", "source_classification", "filters", "source_query",
        "metadata_policy", "microdata_sent_to_llm",
    )
    provenance = {name: dumped["provenance"][name] for name in provenance_keys}
    provenance["source_provenance"] = safe_source_provenance(dumped["provenance"]["source_provenance"])
    return redact({"result": {"operation": "temporal", "data": {"rows": data},
                              "provenance": provenance}}, _secrets())
