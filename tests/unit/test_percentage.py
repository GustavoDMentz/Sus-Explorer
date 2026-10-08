from decimal import Decimal, localcontext
from fractions import Fraction
from copy import deepcopy
import pytest
from sus_explorer.analytics.percentage import percentage_changes, add_percentages
from sus_explorer.streamlit_views import monthly_chart, percentage_summary


def rows(values, periods=None):
    return [{'period': period, 'value': value} for period, value in zip(
        periods or [f'2026-{i+1:02d}' for i in range(len(values))], values)]


@pytest.mark.parametrize('values,expected', [([100,125],'25'), ([100,75],'-25'),
    ([100,100],'0'), ([3,4],'100/3'), ([10**30,10**30+1], '1/10000000000000000000000000000')])
def test_exact_percentage(values, expected):
    original = rows(values)
    backup = deepcopy(original)
    metrics = percentage_changes(original)
    assert metrics[1]['value'] == expected
    assert metrics[1]['classification'] == 'DERIVED'
    assert metrics[1]['unit'] == '%'
    assert original == backup


@pytest.mark.parametrize('values,periods,code', [
    ([0,10],None,'ZERO_DENOMINATOR'), ([None,10],None,'MISSING_VALUE'),
    ([10,None],None,'MISSING_VALUE'), ([10,20],['2026-01','2026-03'],'MISSING_MONTH'),
])
def test_unavailable(values,periods,code):
    metric = percentage_changes(rows(values,periods))[1]
    assert metric['value'] is None
    assert code in [reason['code'] for reason in metric['unavailable_reasons']]


def test_single_month_and_year_boundary():
    assert percentage_changes(rows([10]))[0]['value'] is None
    assert percentage_changes(rows([10,20],['2025-12','2026-01']))[1]['value'] == '100'


@pytest.mark.parametrize('periods', [['2026-02','2026-01'],['2026-01','2026-01']])
def test_order_duplicates(periods):
    with pytest.raises(ValueError):
        percentage_changes(rows([10,20],periods))


def test_decimal_context_and_existing_metrics():
    with localcontext() as context:
        context.prec = 2
        metric = percentage_changes(rows([Decimal('1.00001'),Decimal('1.00002')]))[1]
    assert Fraction(metric['value']) == Fraction(100,100001)
    from sus_explorer.analytics.temporal import TemporalAnalytics
    result = TemporalAnalytics.calculate(rows([10,20,30]), value_key='value',
        start_period='2026-01',end_period='2026-03',source_series_ref='fixture',source_provenance={})
    existing = deepcopy(result.data)
    add_percentages(result)
    for old, new in zip(existing['rows'], result.data['rows']):
        for key in old['metrics']:
            assert old['metrics'][key] == new['metrics'][key]
    assert result.provenance['percentage_change']['source_series_ref'] == 'fixture'


def test_sparse_chart_and_summary():
    observations = rows([100,125,None,150,120])
    for row, metric in zip(observations,percentage_changes(observations)):
        row['metrics'] = {'pct_change':metric}
    result = {'operation':'temporal','data':{'rows':observations},'provenance':{}}
    chart = monthly_chart(result,'pct_change')
    assert chart.data['Valor'].tolist() == [25,-20]
    assert chart.data['Trecho'].nunique() == 2
    assert '25.00%' in percentage_summary(observations)
    assert '20.00%' in percentage_summary(observations)
    assert chart.to_dict()['mark']['type'] == 'bar'
    assert monthly_chart(result).data['Valor'].tolist() == [100,125,150,120]


def test_calendar_placeholders_are_null_and_ticks_bounded():
    from sus_explorer.streamlit_views import calendar_rows, monthly_table
    result = {'operation':'timeseries','data':{'rows':[
        {'period':'2024-01','doses':10},{'period':'2025-12','doses':20}]}}
    original = deepcopy(result)
    display = calendar_rows(result)
    assert len(display) == 24 and display[1]['doses'] is None
    assert len(monthly_table(result)) == 24
    chart = monthly_chart(result)
    spec = chart.to_dict()
    assert len(spec['encoding']['x']['axis']['values']) <= 8
    assert chart.data['Valor'].tolist() == [10,20]
    assert chart.data['Trecho'].nunique() == 2
    assert result == original
