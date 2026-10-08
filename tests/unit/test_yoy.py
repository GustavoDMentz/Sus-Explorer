from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from sus_explorer.schemas import QueryPlan
from sus_explorer.pni import QueryResult
from sus_explorer.analytics.temporal_query import execute_temporal, temporal_answer_payload, TemporalQueryError, SOURCE_LABEL
from sus_explorer.analytics.yoy import add_yoy
from sus_explorer.streamlit_views import monthly_chart
from sus_explorer.llm import GeminiAnalyst, PLANNER

APP=str(Path(__file__).resolve().parents[2]/'app.py')


@pytest.fixture(autouse=True)
def isolate_resource_cache():
    import streamlit as st
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def plan(comparison='yoy',order=1,**extra):
    return QueryPlan.model_validate({'operation':'temporal','uf':'RS','start_year':2026,
        'start_month':1,'end_year':2026,'end_month':3,
        'temporal_analysis':{'order':order,'comparison':comparison}} | extra)


def source(values,year=2026,months=(1,2,3),**provenance):
    return QueryResult('timeseries',{'rows':[{'period':f'{year}-{m:02d}','doses':v}
        for m,v in zip(months,values)]},{'source':SOURCE_LABEL,'uf_partition':'RS','microdata_sent_to_llm':False} | provenance)


def run(current=(110,90,100),previous=(100,100,100),order=1):
    return execute_temporal(plan(order=order),lambda p: source(current) if p.start_year==2026 else source(previous,2025))


def test_yoy_positive_negative_zero_and_january():
    result=run()
    rows=result.data['rows']
    assert [r['metrics']['yoy_delta']['value'] for r in rows]==[10,-10,0]
    assert [r['metrics']['yoy_pct']['value'] for r in rows]==['10','-10','0']
    assert rows[0]['metrics']['yoy_pct']['reference_period']=='2025-01'
    assert result.provenance['period']['start']=='2026-01'
    assert result.provenance['yoy']['reference_period']['start']=='2025-01'
    assert all(r['period'].startswith('2026') for r in rows)
    assert result.provenance['yoy']['classification']=='DERIVED'
    assert result.provenance['yoy']['reference_series_ref'].startswith('timeseries:sha256:')


@pytest.mark.parametrize('previous,code',[(0,'ZERO_DENOMINATOR'),(None,'MISSING_REFERENCE_VALUE')])
def test_zero_or_null_reference(previous,code):
    result=run(previous=(previous,100,100))
    metric=result.data['rows'][0]['metrics']['yoy_pct']
    assert metric['value'] is None
    assert code in [r['code'] for r in metric['unavailable_reasons']]
    if previous==0:
        assert result.data['rows'][0]['metrics']['yoy_delta']['value']==110


def test_sparse_history_uses_calendar_lookup_not_observation_index():
    result=execute_temporal(plan(),lambda p:source([110,200,300]) if p.start_year==2026 else source([100,150],2025,(1,3)))
    assert result.data['rows'][1]['metrics']['yoy_pct']['value'] is None
    assert result.data['rows'][1]['metrics']['yoy_pct']['unavailable_reasons'][0]['code']=='MISSING_REFERENCE_MONTH'
    assert result.data['rows'][2]['metrics']['yoy_pct']['value']=='100'


def test_entire_history_missing_returns_null_not_zero():
    def execute(p):
        if p.start_year==2025: raise FileNotFoundError('no partition')
        return source([10,20,30])
    result=execute_temporal(plan(vaccine_text='influenza'),execute)
    assert all(r['metrics']['yoy_pct']['value'] is None for r in result.data['rows'])
    assert result.data['rows'][0]['value']==10


def test_reference_failure_is_controlled_not_fabricated_absence():
    def execute(p):
        if p.start_year==2025: raise RuntimeError('private credentials')
        return source([10,20,30])
    with pytest.raises(TemporalQueryError) as error:
        execute_temporal(plan(),execute)
    assert error.value.code=='SOURCE_QUERY_FAILED'
    assert 'credentials' not in str(error.value)


def test_identical_filters_and_explicit_historical_query():
    calls=[]
    p=plan(municipality_code='4314902',vaccine_code='33',age_min=10,age_max=30,sex='F')
    def execute(q):
        calls.append(q)
        return source([10,20,30],q.start_year)
    execute_temporal(p,execute)
    assert [q.operation for q in calls]==['timeseries','timeseries']
    assert [q.start_year for q in calls]==[2026,2025]
    for name in ('uf','municipality_code','vaccine_code','age_min','age_max','sex'):
        assert getattr(calls[0],name)==getattr(calls[1],name)==getattr(p,name)


@pytest.mark.parametrize('metadata',[{'uf_partition':'SC'}, {'filters':{'uf':'SC'}}])
def test_inconsistent_reference_filters_rejected(metadata):
    with pytest.raises(TemporalQueryError):
        execute_temporal(plan(),lambda p:source([1,2,3]) if p.start_year==2026 else source([1,2,3],2025,**metadata))


def test_yoy_direct_adapter_rejects_filter_and_interval_mismatch():
    result=run()
    main=result.provenance['source_query']
    reference=deepcopy(result.provenance['yoy']['reference_query'])
    reference['filters']['sex']='M'
    with pytest.raises(ValueError): add_yoy(result,result,main,reference)
    reference=deepcopy(result.provenance['yoy']['reference_query']);reference['start_month']=2
    with pytest.raises(ValueError): add_yoy(result,result,main,reference)


@pytest.mark.parametrize('order',[1,2,3])
def test_monthly_differences_and_mom_percentages_preserved(order):
    values=[1,4,9]
    yoy=run(values,(1,2,3),order)
    mom=execute_temporal(plan('mom',order),lambda _:source(values))
    for yr,mr in zip(yoy.data['rows'],mom.data['rows']):
        assert yr['metrics'][f'delta_{order}']==mr['metrics'][f'delta_{order}']
        assert yr['metrics']['pct_change']==mr['metrics']['pct_change']
    assert yoy.data['summary']==mom.data['summary']


def test_decimal_precision_and_large_integers():
    with localcontext() as context:
        context.prec=2
        result=run((Decimal('1.00002'),10**30+1,4),(Decimal('1.00001'),10**30,3))
    assert Fraction(result.data['rows'][0]['metrics']['yoy_pct']['value'])==Fraction(100,100001)
    assert result.data['rows'][1]['metrics']['yoy_delta']['value']==1
    assert result.data['rows'][2]['metrics']['yoy_pct']['value']=='100/3'


def test_planner_schema_mocks_recognize_yoy_and_legacy_default():
    assert QueryPlan.model_validate(plan().model_dump()).temporal_analysis.comparison=='yoy'
    old=plan().model_dump();del old['temporal_analysis']['comparison']
    assert QueryPlan.model_validate(old).temporal_analysis.comparison=='mom'
    assert 'mesmo mês do ano anterior' in PLANNER
    analyst=GeminiAnalyst.__new__(GeminiAnalyst);analyst.model='mock';analyst.client=Mock()
    analyst.client.models.generate_content.return_value=SimpleNamespace(parsed=plan().model_dump())
    assert analyst.plan('Compare janeiro a março de 2026 no RS com o mesmo mês do ano anterior').temporal_analysis.comparison=='yoy'
    with pytest.raises(ValueError): plan('arbitrary')


def test_external_projection_is_aggregate_only_with_reference_provenance():
    result=run()
    result.data['rows'][0]['patient_id']='private'
    result.provenance['yoy']['reference_provenance']['signed_url']='private'
    payload=temporal_answer_payload(plan(),result)
    text=str(payload)
    assert 'patient_id' not in text and 'signed_url' not in text
    assert payload['result']['data']['rows'][0]['metrics']['yoy_pct']['value']=='10'


def test_broken_percent_bar_keeps_exact_values_and_annotation():
    result=run((400,200,50),(100,100,100)).model_dump()
    original=deepcopy(result)
    chart=monthly_chart(result,'yoy_pct',show_extreme=False)
    assert chart.data['Valor'].tolist()==[300,100,-50]
    assert chart.data['Valor visual'].tolist()==[100,100,-50]
    assert chart.data['Interrompida'].tolist()==[True,False,False]
    assert chart.data['Anotação'].tolist()[0]=='300.00%'
    spec=chart.to_dict()
    assert len(spec['layer'])==3
    assert spec['layer'][1]['mark']['text']=='//'
    assert chart.data['Exato'].tolist()[0]=='300'
    assert monthly_chart(result,'yoy_pct').data['Valor visual'].tolist()[0]==300
    assert result==original


def test_ui_requested_yoy_and_mom_switch_do_not_execute_query(monkeypatch):
    import sus_explorer.service
    service=Mock();monkeypatch.setattr(sus_explorer.service,'SUSExplorer',lambda:service)
    response={'result':run((400,200,50),(100,100,100)).model_dump(),'plan':plan().model_dump(),'answer':None}
    original=deepcopy(response)
    at=AppTest.from_file(APP);at.session_state['query_result']=response;at.run()
    assert not at.exception
    assert at.selectbox[0].value=='Interanual (YoY)'
    assert any('Barra interrompida' in c.value for c in at.caption)
    at.selectbox[0].set_value('Mensal (MoM)').run()
    assert not at.exception
    assert at.session_state['query_result']==original
    service.ask.assert_not_called();service.pni.execute.assert_not_called()


def test_ui_yoy_requires_explicit_click_for_history(monkeypatch):
    import sus_explorer.service
    service=Mock();monkeypatch.setattr(sus_explorer.service,'SUSExplorer',lambda:service)
    mom=execute_temporal(plan('mom'),lambda _:source([10,20,30]))
    response={'result':mom.model_dump(),'plan':plan('mom').model_dump(),'answer':None}
    service.pni.execute.return_value=run((10,20,30),(5,10,15))
    at=AppTest.from_file(APP);at.session_state['query_result']=response;at.run()
    at.selectbox[0].set_value('Interanual (YoY)').run()
    assert not at.exception
    service.pni.execute.assert_not_called()
    next(b for b in at.button if b.label=='Calcular YoY com referência histórica').click().run()
    assert not at.exception
    service.pni.execute.assert_called_once()
    assert at.session_state['query_result']['plan']['temporal_analysis']['comparison']=='yoy'


def test_current_null_and_missing_month_never_become_zero():
    result=execute_temporal(plan(),lambda p:source([None,200],2026,(1,3)) if p.start_year==2026 else source([100,100,100],2025))
    rows=result.data['rows']
    assert rows[0]['metrics']['yoy_delta']['value'] is None
    assert rows[1]['metrics']['yoy_pct']['value'] is None
    assert rows[1]['metrics']['yoy_pct']['unavailable_reasons'][0]['code']=='MISSING_MONTH'
    assert rows[2]['metrics']['yoy_pct']['value']=='100'


def test_earliest_main_year_has_explicit_reference_not_invented_observations():
    queries=[]
    def execute(q):
        queries.append(q)
        if q.start_year==2019: raise FileNotFoundError()
        return source([1,2,3],2020)
    result=execute_temporal(plan(start_year=2020,end_year=2020),execute)
    assert queries[1].start_year==2019
    assert result.provenance['yoy']['reference_query']['start_year']==2019
    assert result.data['rows'][0]['metrics']['yoy_pct']['reference_value'] is None


def test_real_pyarrow_backend_keeps_same_sex_and_vaccine_filters():
    import pyarrow as pa
    import pyarrow.dataset as ds
    from sus_explorer.pni import PNIRemote
    backend=PNIRemote.__new__(PNIRemote)
    def dataset(year,month,uf):
        n=month * (2 if year==2026 else 1)
        return ds.dataset(pa.table({'co_vacina':['33']*n+['33','99'],
                                    'tp_sexo_paciente':['F']*n+['M','F']}))
    backend.dataset=dataset
    result=backend.execute(plan(vaccine_code='33',sex='F'))
    assert [r['value'] for r in result.data['rows']]==[2,4,6]
    assert [r['metrics']['yoy_pct']['reference_value'] for r in result.data['rows']]==[1,2,3]
    assert [r['metrics']['yoy_pct']['value'] for r in result.data['rows']]==['100']*3


def test_yoy_resolved_vaccine_mismatch_is_rejected():
    resolution={'method':'source_text_or_authoritative_code_v1','terminology_source':'MS + SES-GO','resolved_codes':['33']}
    def execute(q):
        modified=deepcopy(resolution)
        if q.start_year==2025: modified['resolved_codes']=['77']
        return source([1,2,3],q.start_year,vaccine_filter=modified)
    with pytest.raises(TemporalQueryError) as error:
        execute_temporal(plan(vaccine_text='influenza'),execute)
    assert error.value.code=='INVALID_REFERENCE_SERIES'
