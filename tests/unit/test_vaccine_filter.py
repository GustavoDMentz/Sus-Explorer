from copy import deepcopy
import pyarrow as pa
import pyarrow.dataset as ds
import pytest
from sus_explorer.terminology import ImmunobiologicalTerminology, terminology
from sus_explorer.pni import PNIRemote
from sus_explorer.schemas import QueryPlan


@pytest.fixture
def vocabulary(monkeypatch):
    glossary=ImmunobiologicalTerminology()
    glossary._payload={'concepts':{
        '33':{'official_display':'INF3','definition':'Vacina influenza trivalente','conflict':False},
        '77':{'official_display':'INF4','definition':'Vacina influenza tetravalente','conflict':False},
        '99':{'official_display':'OUTRA','definition':'Vacina influenza inválida','conflict':True},
    },'ms':{'version':'test-ms'},'ses_go':{'version':'test-go'}}
    monkeypatch.setattr(terminology,'load',lambda:glossary._payload)
    monkeypatch.setattr(terminology,'metadata',lambda:glossary._payload)
    return glossary


def test_resolve_family_without_guessed_codes_and_ignore_conflicts(vocabulary):
    assert vocabulary.resolve_text('INFLUENZA') == ['33','77']
    assert vocabulary.resolve_text('INF3') == ['33']
    assert vocabulary.resolve_text('trivalente') == ['33']
    assert vocabulary.resolve_text('inexistente') == []


def make_backend():
    backend=PNIRemote.__new__(PNIRemote)
    def dataset(year,month,uf):
        return ds.dataset(pa.table({'co_vacina':['33','77','99',None,'99'],
            'ds_vacina':['INF3','INF4','OUTRA',None,'INFLUENZA'],
            'tp_sexo_paciente':['F','F','F','F','M']}))
    backend.dataset=dataset
    return backend


def plan(**kwargs):
    return QueryPlan(operation='temporal',uf='RS',start_year=2026,start_month=1,
        end_year=2026,end_month=6,temporal_analysis={'order':1},vaccine_text='influenza',**kwargs)


def test_influenza_codes_and_direct_text_union_are_counted_once(vocabulary):
    backend=make_backend()
    result=backend.execute(plan())
    assert [row['value'] for row in result.data['rows']] == [3]*6
    assert [row['metrics']['delta_1']['value'] for row in result.data['rows']] == [None,0,0,0,0,0]
    provenance=result.provenance['source_provenance']['vaccine_filter']
    assert provenance['resolved_codes'] == ['33','77']
    assert provenance['ms_version'] == 'test-ms'
    assert result.provenance['filters']['vaccine_text'] == 'influenza'


def test_other_filters_and_explicit_code_are_preserved(vocabulary):
    assert make_backend().execute(plan(sex='F')).data['rows'][0]['value'] == 2
    assert make_backend().execute(plan(vaccine_code='33')).data['rows'][0]['value'] == 1


def test_missing_month_remains_null_with_resolved_filter(vocabulary):
    backend=make_backend();original=backend.dataset
    def dataset(year,month,uf):
        if month == 3: raise FileNotFoundError()
        return original(year,month,uf)
    backend.dataset=dataset
    rows=backend.execute(plan()).data['rows']
    assert rows[2]['value'] is None
    assert rows[2]['metrics']['delta_1']['value'] is None
    assert rows[3]['metrics']['delta_1']['value'] is None
    assert rows[4]['metrics']['delta_1']['value'] == 0


def test_no_filter_keeps_total_and_unavailable_terminology_cannot_fabricate_zero(vocabulary,monkeypatch):
    backend=make_backend()
    assert backend.timeseries(QueryPlan(operation='timeseries',uf='RS',start_year=2026,
        start_month=1,end_year=2026,end_month=1)).data['rows'][0]['doses'] == 5
    monkeypatch.setattr(terminology,'load',lambda: (_ for _ in ()).throw(RuntimeError('offline')))
    from sus_explorer.analytics.temporal_query import TemporalQueryError
    with pytest.raises(TemporalQueryError) as error:
        backend.execute(plan())
    assert error.value.code == 'SOURCE_QUERY_FAILED'


def test_text_and_code_matching_same_row_never_double_count(vocabulary):
    backend=PNIRemote.__new__(PNIRemote)
    table=pa.table({'co_vacina':['33'],'ds_vacina':['INFLUENZA']})
    backend.dataset=lambda *_:ds.dataset(table)
    assert backend.execute(plan()).data['rows'][0]['value'] == 1


def test_varying_resolved_monthly_counts_produce_exact_differences(vocabulary):
    backend=PNIRemote.__new__(PNIRemote)
    counts=[1,2,4,7,11,16]
    backend.dataset=lambda year,month,uf:ds.dataset(pa.table({
        'co_vacina':['33']*counts[month-1]+['99'],
        'ds_vacina':['INF3']*counts[month-1]+['OUTRA']}))
    rows=backend.execute(plan()).data['rows']
    assert [row['value'] for row in rows] == counts
    assert [row['metrics']['delta_1']['value'] for row in rows] == [None,1,2,3,4,5]
