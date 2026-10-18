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
