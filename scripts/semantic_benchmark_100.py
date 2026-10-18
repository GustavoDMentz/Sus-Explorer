"""100-case semantic benchmark: deterministic routing, optionally Gemini baseline.

Default: offline, no credentials, no API calls.
Opt-in: --gemini invokes the existing GeminiAnalyst with deterministic mode disabled.
This is a planner benchmark: no R2 queries or answer-generation calls.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from sus_explorer.deterministic_planner import deterministic_plan

MONTHS = ("janeiro", "fevereiro", "março", "abril", "maio", "junho",
          "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
UFS = ("RS", "SP", "RJ", "MG", "BA", "PR", "SC", "PE", "CE", "AM")


def cases():
    """Exactly 100 independently specified routing/field expectations."""
    result = []
    # 40 count cases, deliberately varied by UF, month, year and wording.
    for i in range(40):
        uf = UFS[i % len(UFS)]
        month = i % 12 + 1
        year = 2024 + i % 3
        prefix = ("Quantas doses foram aplicadas", "Qual o total de doses",
                  "Total de doses", "Quantas doses foram aplicadas")[i % 4]
        question = f"{prefix} no {uf} em {MONTHS[month - 1]} de {year}?"
        result.append({"id": f"count-{i:02d}", "question": question,
                       "route": "regex", "expected": {"operation": "count",
                       "uf": uf, "year": year, "month": month}})
    # 20 explicit monthly finite-difference questions.
    for i in range(20):
        uf = UFS[i % len(UFS)]
        order = i % 3 + 1
        phrase = ("Qual foi a variação mensal das doses",
                  "Calcule a segunda diferença das doses",
                  "Calcule a terceira diferença das doses")[order - 1]
        start, end = i % 6 + 1, i % 6 + 7
        year = 2024 + i % 3
        question = f"{phrase} no {uf} entre {MONTHS[start - 1]} e {MONTHS[end - 1]} de {year}?"
        result.append({"id": f"temporal-{i:02d}", "question": question,
                       "route": "regex", "expected": {"operation": "temporal",
                       "uf": uf, "start_year": year, "start_month": start,
                       "end_year": year, "end_month": end,
                       "temporal_analysis.order": order,
                       "temporal_analysis.comparison": "mom"}})
    # 40 adversarial cases: any partial match would silently discard intent.
    suffixes = (
        ", apenas mulheres", ", apenas homens", ", por município",
        ", em Porto Alegre", ", só influenza", ", contra COVID-19",
        ", em menores de cinco anos", ", por faixa etária",
        ", excluindo doses de reforço", ", agrupadas por vacina",
        ", por estabelecimento", ", apenas primeira dose",
        ", em pacientes com 60 anos", ", com taxa de cobertura",
        ", em relação à população", ", sem registros duplicados",
        ", em 15 de maio", ", no primeiro trimestre",
        ", comparando com 2025", ", ordenadas por município",
    )
    for i in range(40):
        uf = UFS[i % len(UFS)]
        year = 2024 + i % 3
        suffix = suffixes[i % len(suffixes)]
        base = (f"Quantas doses foram aplicadas no {uf} em maio de {year}"
                if i < 20 else
                f"Qual foi a variação mensal das doses no {uf} entre março e agosto de {year}")
        question = base + suffix + "?"
        result.append({"id": f"fallback-{i:02d}", "question": question,
                       "route": "llm", "expected": None})
    assert len(result) == 100
    assert len({item["question"] for item in result}) == 100
    return result


def get_field(plan, dotted):
    value = plan
    for part in dotted.split("."):
        value = getattr(value, part, None)
        if value is None:
            return None
    return value


def run(*, gemini=False):
    analyst = None
    if gemini:
        # The baseline must bypass the experimental regex path.
        os.environ.pop("SUS_DETERMINISTIC_PLANNER", None)
        from sus_explorer.llm import GeminiAnalyst
        analyst = GeminiAnalyst()

    rows = []
    for case in cases():
        t0 = time.perf_counter()
        regex_plan = deterministic_plan(case["question"])
        regex_ms = round((time.perf_counter() - t0) * 1000, 3)
        route = "regex" if regex_plan is not None else "llm"
        expected = case["expected"]
        field_errors = ({field: {"expected": value, "actual": get_field(regex_plan, field)}
                         for field, value in expected.items()
                         if regex_plan is not None and get_field(regex_plan, field) != value}
                        if expected is not None else {})
        passed = route == case["route"] and not field_errors
        row = {"id": case["id"], "question": case["question"],
               "expected_route": case["route"], "actual_route": route,
               "regex_ms": regex_ms, "regex_pass": passed,
               "field_errors": field_errors,
               "regex_plan": regex_plan.model_dump(mode="json") if regex_plan else None}
        if analyst is not None:
            started = time.perf_counter()
            try:
                baseline = analyst.plan(case["question"])
                row["gemini_plan"] = baseline.model_dump(mode="json")
                row["gemini_error"] = None
                row["gemini_expected_field_errors"] = (
                    {field: {"expected": value, "actual": get_field(baseline, field)}
                     for field, value in expected.items()
                     if get_field(baseline, field) != value}
                    if expected else None)
                row["gemini_matches_regex"] = (
                    baseline.model_dump(exclude_none=True) ==
                    regex_plan.model_dump(exclude_none=True)
                    if regex_plan else None)
            except Exception as exc:
                row["gemini_plan"] = None
                row["gemini_error"] = type(exc).__name__
            row["gemini_ms"] = round((time.perf_counter() - started) * 1000, 2)
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gemini", action="store_true",
                        help="Opt in to up to 100 real Gemini planning requests (plus retries).")
    parser.add_argument("--output", default="semantic_benchmark_100.json")
    args = parser.parse_args()
    rows = run(gemini=args.gemini)
    summary = {"total": len(rows),
               "regex_pass": sum(row["regex_pass"] for row in rows),
               "regex_coverage": sum(row["actual_route"] == "regex" for row in rows),
               "false_positive_routes": sum(row["expected_route"] == "llm"
                                            and row["actual_route"] == "regex" for row in rows),
               "gemini_enabled": args.gemini,
               "gemini_errors": sum(bool(row.get("gemini_error")) for row in rows)}
    path = Path(args.output)
    path.write_text(json.dumps({"summary": summary, "cases": rows},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Detailed report: {path}")
    if summary["regex_pass"] != summary["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
