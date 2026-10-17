"""Regression tests for the conservative deterministic planner."""
from sus_explorer.deterministic_planner import deterministic_plan


def test_count_month():
    plan = deterministic_plan("Quantas doses foram aplicadas no RS em maio de 2026?")
    assert plan is not None
    assert plan.operation == "count"
    assert (plan.uf, plan.year, plan.month) == ("RS", 2026, 5)


def test_count_whole_year():
    plan = deterministic_plan("Quantas doses foram aplicadas no RS em 2025?")
    assert plan is not None
    assert (plan.operation, plan.year, plan.month) == ("count", 2025, None)


def test_temporal_order():
    for expression, order in (
        ("Qual foi a variação mensal das doses", 1),
        ("Calcule a segunda diferença das doses", 2),
        ("Calcule a terceira diferença das doses", 3),
    ):
        plan = deterministic_plan(f"{expression} no RS entre março e agosto de 2026?")
        assert plan is not None
        assert plan.temporal_analysis.order == order
        assert plan.temporal_analysis.comparison == "mom"


def test_no_partial_interpretation():
    questions = [
        "Quantas doses foram aplicadas no RS em maio de 2026, apenas mulheres?",
        "Quantas doses foram aplicadas no RS em maio de 2026 por município?",
        "Quantas doses foram aplicadas no RS em 15 de maio de 2026?",
        "Quantas doses foram aplicadas no RS em maio?",
        "Qual foi a cobertura vacinal no RS em maio de 2026?",
        "Compare as doses no RS de janeiro a junho de 2026 com os mesmos meses de 2025.",
        "Calcule a segunda diferença das doses no RS entre março e agosto de 2026, por sexo?",
        "Calcule a terceira diferença das doses no RS entre dezembro e janeiro de 2026?",
    ]
    assert all(deterministic_plan(question) is None for question in questions)
