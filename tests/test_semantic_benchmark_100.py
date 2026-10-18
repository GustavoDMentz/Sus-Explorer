"""Offline contract for the 100-case semantic benchmark."""
from scripts.semantic_benchmark_100 import cases, run


def test_benchmark_has_100_unique_cases():
    items = cases()
    assert len(items) == 100
    assert len({case["question"] for case in items}) == 100
    assert sum(case["route"] == "regex" for case in items) == 60
    assert sum(case["route"] == "llm" for case in items) == 40


def test_benchmark_regex_semantics_and_fallback():
    rows = run(gemini=False)
    assert all(row["regex_pass"] for row in rows), [
        (row["id"], row["field_errors"], row["actual_route"])
        for row in rows if not row["regex_pass"]
    ]


def test_gemini_error_diagnostics_do_not_expose_messages():
    from scripts.semantic_benchmark_100 import classify_gemini_error

    class FakeClientError(Exception):
        code = 429

    detail = classify_gemini_error(FakeClientError("secret-key-in-error"))
    assert detail == {"type": "FakeClientError", "category": "rate_limit", "http_status": 429}
    assert "secret-key-in-error" not in str(detail)


def test_gemini_planner_response_diagnostic():
    from scripts.semantic_benchmark_100 import classify_gemini_error
    from sus_explorer.llm import PlannerResponseError

    detail = classify_gemini_error(PlannerResponseError())
    assert detail["category"] == "planner_response"
    assert detail["http_status"] is None
