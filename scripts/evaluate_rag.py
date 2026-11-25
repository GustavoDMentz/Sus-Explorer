"""Reproducible qualitative RAG evaluation against real configured services."""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from sus_explorer.rag import INSUFFICIENT_CONTEXT


DEFAULT_CASES = Path(__file__).parents[1] / "tests/fixtures/rag_evaluation_cases.json"


def load_cases(path: Path) -> list[dict]:
    rows = json.loads(path.read_text("utf-8"))
    required = {"id", "question", "expected_intent", "expected_source",
                "required_evidence_terms", "forbidden_answer_terms"}
    if (not isinstance(rows, list) or not rows or
            any(not isinstance(row, dict) or set(row) != required for row in rows) or
            len({row["id"] for row in rows}) != len(rows)):
        raise ValueError("Casos RAG inválidos")
    return rows


def classify_payload(payload: dict) -> str:
    if payload.get("planner_source") == "scope_guard":
        return "out_of_scope"
    if payload.get("needs_clarification"):
        return "clarification"
    if payload.get("plan", {}).get("operation") == "document":
        return ("insufficient_evidence" if payload.get("answer") == INSUFFICIENT_CONTEXT
                else "document")
    if payload.get("sources"):
        return "hybrid"
    return "analytic"


def objective_checks(case: dict, payload: dict, elapsed_seconds: float,
                     evidence_by_id: dict[str, str] | None = None) -> dict:
    answer = payload.get("answer") or payload.get("clarification_question") or ""
    sources = payload.get("sources") or []
    citation_ids = [source.get("citationId") for source in sources]
    used_ids = re.findall(r"`([^`]+#chunk-[0-9]+)`", answer)
    evidence_by_id = evidence_by_id or {}
    cited_text = " ".join(evidence_by_id.get(item, "") for item in used_ids)
    required_terms = case["required_evidence_terms"]
    return {
        "intent": classify_payload(payload) == case["expected_intent"],
        "forbidden_terms_absent": not any(
            term.casefold() in answer.casefold() for term in case["forbidden_answer_terms"]),
        "citation_ids_unique": len(citation_ids) == len(set(citation_ids)),
        "citations_verifiable": all(
            isinstance(item, str) and "#chunk-" in item for item in citation_ids),
        "used_citations_were_retrieved": all(item in citation_ids for item in used_ids),
        "required_terms_in_cited_evidence": (
            all(term.casefold() in cited_text.casefold() for term in required_terms)
            if required_terms else True),
        "has_sources_when_expected": (bool(sources) if case["expected_source"] in
                                      ("project_docs", "postgres+project_docs") else True),
        "latency_recorded": elapsed_seconds >= 0,
    }


def run(cases: list[dict]) -> list[dict]:
    from sus_explorer.service import SUSExplorer
    explorer = SUSExplorer()
    results = []
    for case in cases:
        started = time.perf_counter()
        try:
            payload = explorer.ask(case["question"])
            error = None
        except Exception as exc:
            payload = {}
            error = type(exc).__name__
        elapsed = round(time.perf_counter() - started, 3)
        evidence_by_id = {}
        if not error and payload.get("sources"):
            for hit in explorer.knowledge.search(case["question"]):
                evidence_by_id[f"{hit['original_reference']}#chunk-{hit['chunk_index']}"] = hit["content"]
        checks = objective_checks(case, payload, elapsed, evidence_by_id) if not error else {}
        results.append({"id": case["id"], "question": case["question"],
                        "expected_intent": case["expected_intent"],
                        "actual_intent": classify_payload(payload) if payload else None,
                        "elapsed_seconds": elapsed, "checks": checks,
                        "passed": bool(checks) and all(checks.values()),
                        "error_type": error, "payload": payload,
                        "cited_evidence": {key: evidence_by_id[key] for key in
                                           re.findall(r"`([^`]+#chunk-[0-9]+)`",
                                                      payload.get("answer") or "")
                                           if key in evidence_by_id}})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=Path("rag-evaluation.json"))
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    cases = load_cases(args.cases)
    if args.validate_only:
        print(json.dumps({"cases": len(cases), "valid": True}, ensure_ascii=False))
        return 0
    rows = run(cases)
    report = {"summary": {"total": len(rows), "passed": sum(r["passed"] for r in rows),
                          "errors": sum(bool(r["error_type"]) for r in rows)},
              "cases": rows}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["summary"]["passed"] == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
