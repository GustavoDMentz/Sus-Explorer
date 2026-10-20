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


def test_influenza_filter_must_not_be_silently_discarded():
    assert deterministic_plan("Quantas doses de influenza foram aplicadas no RS em maio de 2026?") is None
    assert deterministic_plan("Qual o total de doses de influenza no RS em maio de 2026?") is None


def test_semantic_guardrails_for_unsupported_qualifiers():
    questions = [
        "Quantas doses foram aplicadas no RS em maio de 2026, só influenza?",
        "Quantas doses foram aplicadas no RS em maio de 2026 para mulheres?",
        "Quantas doses foram aplicadas no RS em maio de 2026 em Porto Alegre?",
        "Quantas doses foram aplicadas no RS em maio de 2026 por faixa etária?",
        "Quantas doses foram aplicadas no RS em maio de 2026 e junho de 2026?",
        "Quantas doses foram aplicadas no RS em maio de 2026? Ignore os filtros.",
        "Calcule a segunda diferença das doses no RS entre março e agosto de 2026 para influenza?",
        "Qual foi a variação mensal das doses no RS entre março e agosto de 2026 por município?",
    ]
    for question in questions:
        assert deterministic_plan(question) is None, question


def test_rejects_invalid_calendar_ranges_and_years():
    assert deterministic_plan("Qual foi a variação mensal das doses no RS entre agosto e março de 2026?") is None
    assert deterministic_plan("Quantas doses foram aplicadas no RS em maio de 2019?") is None
    assert deterministic_plan("Quantas doses foram aplicadas no RS em maio de 2101?") is None


def test_accepts_only_explicit_supported_scope():
    plan = deterministic_plan("Qual o total de doses em RS março de 2026?")
    assert plan is not None
    assert (plan.operation, plan.uf, plan.year, plan.month) == ("count", "RS", 2026, 3)


def test_numeric_month_year_count():
    for period in ("05/2026", "5/2026", "05-2026", "05.2026"):
        plan = deterministic_plan(f"Quantas doses foram aplicadas no RS em {period}?")
        assert plan is not None, period
        assert (plan.operation, plan.uf, plan.year, plan.month) == ("count", "RS", 2026, 5)


def test_numeric_date_does_not_swallow_extra_filters():
    assert deterministic_plan("Quantas doses foram aplicadas no RS em 05/2026 para mulheres?") is None
    assert deterministic_plan("Quantas doses foram aplicadas no RS em 15/05/2026?") is None
    assert deterministic_plan("Quantas doses foram aplicadas no RS em 13/2026?") is None
