from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest
from sus_explorer.analytics.percentage import summarize_series, add_percentages
from sus_explorer.analytics.temporal import TemporalAnalytics
from sus_explorer.streamlit_views import contextual_summary, monthly_chart, monthly_table

APP = str(Path(__file__).resolve().parents[2] / 'app.py')


def observations(values, periods=None):
    return [{'period': p, 'value': v} for p, v in zip(
        periods or [f'2026-{i+1:02d}' for i in range(len(values))], values)]


def payload(values=(10,20,1000,2000,500,None,250), vaccine='influenza'):
    result = TemporalAnalytics.calculate(observations(values), value_key='value',
        start_period='2026-01', end_period=f'2026-{len(values):02d}',
        source_series_ref='fixture:seasonal', source_provenance={})
    result.operation = 'temporal'
    result.provenance.update(order=1, formula='y(t) - y(t-1)', filters={'vaccine_text': vaccine})
    add_percentages(result)
    return {'result': result.model_dump(), 'plan': {}, 'answer':'Texto não usado no resumo determinístico.'}


def test_abrupt_growth_peak_decline_and_gap():
    data = payload()['result']['data']
    summary = data['summary']
    assert summary['observed_total'] == '3780'
    assert summary['total_is_partial']
    assert summary['peak'] == {'value':'2000','periods':['2026-04']}
    assert summary['greatest_absolute_changes'][0]['absolute_change'] == '-1500'
    assert [t['period'] for t in summary['declines_after_last_peak']] == ['2026-05']
    assert summary['extreme_increases'][0]['pct_change'] == '4900'
    assert summary['extreme_increases'][0]['previous_value'] == '20'
    text = contextual_summary(summary)
    assert 'abr/26' in text and 'mai/26' in text
    assert 'jul/26' not in text.split('houve redução')[1]
    assert 'caus' not in text and 'campanha' not in text


def test_focused_and_full_percentage_views_preserve_exact_result():
    result = payload()['result']
    original = deepcopy(result)
    focused = monthly_chart(result,'pct_change',show_extreme=False)
    full = monthly_chart(result,'pct_change',show_extreme=True)
    assert 4900 not in focused.data['Valor'].tolist()
    assert 4900 in full.data['Valor'].tolist()
    assert 100 in focused.data['Valor'].tolist()  # boundary not excluded
    assert -75 in focused.data['Valor'].tolist()
    assert result['data']['rows'][2]['metrics']['pct_change']['value'] == '4900'
    assert monthly_table(result).iloc[2]['pct_change (DERIVED)'] == '4900'
    assert result == original
    assert monthly_chart(result).data['Valor'].tolist() == [10,20,1000,2000,500,250]


def test_zero_denominator_still_has_absolute_transition():
    result = payload((0,100,50))['result']
    rows = result['data']['rows']
    assert rows[1]['metrics']['pct_change']['value'] is None
    assert rows[1]['metrics']['delta_1']['value'] == 100
    summary = result['data']['summary']
    assert summary['extreme_increases'] == []
    assert summary['greatest_absolute_changes'][0]['absolute_change'] == '100'
    assert summary['observed_total'] == '150'


def test_no_transition_across_absent_month_or_null():
    summary = summarize_series(observations([10,1000,None,0,20],
        ['2025-12','2026-02','2026-03','2026-04','2026-05']))
    assert summary['extreme_increases'] == []
    assert summary['greatest_absolute_changes'][0]['absolute_change'] == '20'
    assert summary['declines_after_last_peak'] == []


@pytest.mark.parametrize('values,total,peaks', [
    ([],None,[]), ([None,None],None,[]), ([0],'0',['2026-01']),
    ([10,10,10],'30',['2026-01','2026-02','2026-03']),
])
def test_missing_single_and_tied_peaks(values,total,peaks):
    summary = summarize_series(observations(values))
    assert summary['observed_total'] == total
    assert summary['peak']['periods'] == peaks
    assert summary['extreme_increases'] == []


def test_summary_precision_independent_of_decimal_context():
    values = [Decimal('100000000000000000000000000.00001'),
              Decimal('100000000000000000000000000.00002')]
    with localcontext() as context:
        context.prec = 2
        summary = summarize_series(observations(values))
    assert Fraction(summary['observed_total']) == sum(map(Fraction,values))
    assert summary['greatest_absolute_changes'][0]['absolute_change'] == '0.00001'


def test_ui_hierarchy_full_scale_toggle_and_no_new_query(monkeypatch):
    import sus_explorer.service
    service = Mock()
    monkeypatch.setattr(sus_explorer.service,'SUSExplorer',lambda:service)
    response = payload()
    original = deepcopy(response)
    at = AppTest.from_file(APP)
    at.session_state['query_result'] = response
    at.run()
    assert not at.exception
    titles = [item.value for item in at.subheader]
    assert titles.index('Resumo') < titles.index('Volume mensal · DIRECT — Observado') < titles.index('Dinâmica mensal · DERIVED — Calculado') < titles.index('Interpretação · DERIVED — Calculado')
    assert any('base de comparação pequena' in item.value for item in at.warning)
    assert any('campanha' in item.value and 'não permitem atribuir' in item.value for item in at.caption)
    assert at.checkbox[0].value is False
    at.checkbox[0].check().run()
    assert not at.exception
    assert at.checkbox[0].value is True
    assert at.session_state['query_result'] == original
    service.ask.assert_not_called()
    at.radio[0].set_value('Diferença absoluta').run()
    assert not at.exception
    service.ask.assert_not_called()


def test_non_influenza_and_all_missing_do_not_get_campaign_claim():
    for response in (payload(vaccine='hepatite'), payload((None,None)), payload((10,10,10))):
        at = AppTest.from_file(APP)
        at.session_state['query_result'] = response
        at.run()
        assert not at.exception
        assert not any('dinâmica sazonal' in item.value for item in at.caption)
