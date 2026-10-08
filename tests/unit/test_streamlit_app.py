from copy import deepcopy
from unittest.mock import Mock
from decimal import Decimal
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from sus_explorer.streamlit_views import chart_number, monthly_chart, monthly_table

APP = str(Path(__file__).resolve().parents[2] / 'app.py')


def response():
    return {'needs_clarification':False, 'plan':{'operation':'temporal'}, 'answer':'Agregado calculado.',
        'result':{'operation':'temporal','data':{'rows':[
            {'period':f'2026-{i:02}', 'value':i*10, 'metrics':{'delta_1':{
                'value': None if i == 1 else 10, 'unavailable_reasons':[
                    {'code':'INSUFFICIENT_HISTORY','period':'2025-12'}] if i == 1 else []}}}
            for i in range(1,4)]}, 'provenance':{'order':1,'classification':'DERIVED',
            'formula':'y(t) - y(t-1)', 'units':{'delta_1':'doses/month^1'},
            'source_provenance':{'elapsed_seconds':139.491,'parquet_fragments':207}},'warnings':[]}}


def test_form_only_runs_on_submit_and_preserves_result_across_reruns(monkeypatch):
    import sus_explorer.service
    service = Mock()
    service.ask.return_value = response()
    monkeypatch.setattr(sus_explorer.service, 'SUSExplorer', lambda: service)
    at = AppTest.from_file(APP).run()
    assert not at.exception
    service.ask.assert_not_called()
    at.text_area[0].set_value('Variação mensal no RS de janeiro a março de 2026?').run()
    service.ask.assert_not_called()
    at.text_area[0].set_value('Variação mensal no RS de janeiro a março de 2026?')
    at.button[0].click().run()
    assert not at.exception
    monthly_tables = [table.value for table in at.dataframe
                      if 'Doses/registros (DIRECT)' in table.value.columns]
    assert len(monthly_tables) == 1
    assert monthly_tables[0]['Doses/registros (DIRECT)'].tolist() == ['10', '20', '30']
    assert len(at.get('vega_lite_chart')) == 2
    service.ask.assert_called_once()
    at.run()
    assert not at.exception
    service.ask.assert_called_once()


def test_exact_table_and_chart_do_not_bridge_nulls_or_absent_months():
    payload = response()['result']
    original = deepcopy(payload)
    rows = payload['data']['rows']
    rows[1]['metrics']['delta_1']['value'] = None
    rows.append({'period':'2026-05','value':50,'metrics':{'delta_1':{'value':10}}})
    chart = monthly_chart(payload, 'delta_1')
    frame = chart.data
    assert frame['Trecho'].nunique() == 2
    assert frame['Valor'].tolist() == [10,10]
    rows[0]['value'] = 2**53 + 1
    assert monthly_table(payload).iloc[0]['Doses/registros (DIRECT)'] == str(2**53+1)
    assert monthly_chart(payload).data['Valor'].tolist() == [20,30,50]
    assert original['data']['rows'][0]['value'] == 10


@pytest.mark.parametrize('value', [None, True, 2**53+1, Decimal('1.00000000000000000001'), 'NaN', 'Infinity'])
def test_unsafe_chart_values_are_omitted(value):
    assert chart_number(value) is None


def test_empty_and_exact_zero_charts():
    assert chart_number(0) == 0
    assert chart_number(Decimal('0.1')) == 0.1
    assert monthly_chart({'operation':'timeseries','data':{'rows':[]}}) is None


@pytest.mark.parametrize('operation,data', [
    ('count', {'doses':1179648}),
    ('group', {'rows':[{'value':'RS','count':10}]}),
    ('latency', {'median_days':2,'p90_days':4,'p95_days':5}),
    ('timeseries', {'rows':[{'period':'2026-01','doses':0},{'period':'2026-03','doses':10}]}),
])
def test_existing_operations_render_without_backend_initialization(operation,data):
    at = AppTest.from_file(APP)
    at.session_state['query_result'] = {'result':{'operation':operation,'data':data,'provenance':{}},'answer':'Resultado'}
    at.run()
    assert not at.exception


def test_clarification_renders_without_chart():
    at = AppTest.from_file(APP)
    at.session_state['query_result'] = {'needs_clarification':True,'clarification_question':'Qual UF?','plan':{}}
    at.run()
    assert not at.exception
    assert at.warning[0].value == 'Qual UF?'
    assert not at.dataframe


def test_percent_toggle_preserves_result_and_never_calls_service(monkeypatch):
    import sus_explorer.service
    from sus_explorer.analytics.percentage import percentage_changes
    service = Mock()
    monkeypatch.setattr(sus_explorer.service, 'SUSExplorer', lambda: service)
    payload = response()
    rows = payload['result']['data']['rows']
    for row, metric in zip(rows, percentage_changes(rows)):
        row['metrics']['pct_change'] = metric
    original = deepcopy(payload)
    at = AppTest.from_file(APP)
    at.session_state['query_result'] = payload
    at.run()
    assert not at.exception
    assert at.radio[0].value == 'Variação percentual'
    assert len(at.get('vega_lite_chart')) == 2
    at.radio[0].set_value('Diferença absoluta').run()
    assert not at.exception
    service.ask.assert_not_called()
    assert at.session_state['query_result'] == original
