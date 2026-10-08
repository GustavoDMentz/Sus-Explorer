import pytest
from sus_explorer.llm import apply_whole_year_interval, GeminiAnalyst
from sus_explorer.schemas import QueryPlan
from types import SimpleNamespace
from unittest.mock import Mock


def partial(**changes):
    return QueryPlan.model_validate({'operation':'temporal','uf':'RS','temporal_analysis':{'order':1},
        'status':'needs_clarification','missing':['start_month','end_month'],
        'clarification_question':'Quais meses?','start_year':2024,'end_year':2025} | changes)


@pytest.mark.parametrize('interval', ['de 2024 a 2025','entre 2024 e 2025','2024 até 2025'])
def test_year_only_interval_does_not_require_months(interval):
    plan = apply_whole_year_interval(f'Qual a variação mensal das doses no RS {interval}?',partial())
    assert plan.status == 'ready'
    assert (plan.start_year,plan.start_month,plan.end_year,plan.end_month) == (2024,1,2025,12)
    assert plan.missing == [] and plan.clarification_question is None


def test_other_missing_parameters_still_require_clarification():
    plan = apply_whole_year_interval('Variação de 2024 a 2025?', partial(uf=None, missing=['uf','start_month','end_month']))
    assert plan.status == 'needs_clarification' and plan.missing == ['uf']


@pytest.mark.parametrize('question', ['Janeiro a junho de 2024 em relação a 2025?',
    'Variação em maio de 2024 a 2025?', 'Primeiro semestre de 2024 a 2025?',
    'Variação de 2024 a 2025 e de 2026 a 2027?', 'Variação de 2025 a 2024?',
    'Variação no RS?', 'Variação entre 2024 e 2025 de 01/02/2024 a 01/05/2025?'])
def test_no_expansion_of_subranges_comparisons_or_ambiguous_ranges(question):
    original=partial()
    assert apply_whole_year_interval(question,original) == original


def test_planner_integration_releases_only_missing_months():
    analyst=GeminiAnalyst.__new__(GeminiAnalyst)
    analyst.model='test-model';analyst.client=Mock()
    analyst.client.models.generate_content.return_value=SimpleNamespace(parsed=partial().model_dump())
    result=analyst.plan('Qual a variação mensal no RS de 2024 a 2025?')
    assert result.status == 'ready' and result.start_month == 1 and result.end_month == 12


def test_count_contract_remains_unchanged():
    p=QueryPlan(operation='count',uf='RS',year=2024)
    assert apply_whole_year_interval('Doses de 2024 a 2025',p) == p
