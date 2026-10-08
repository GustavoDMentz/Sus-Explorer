from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock
import re

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from sus_explorer.streamlit_provenance import (PROVENANCE_STYLES, provenance_label,
    badge_html, documented_enrichment, style_provenance_table)
from sus_explorer.streamlit_views import monthly_chart

APP = str(Path(__file__).resolve().parents[2] / 'app.py')


def luminance(color):
    components = [int(color[i:i+2],16)/255 for i in (1,3,5)]
    linear = [c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in components]
    return sum(c*w for c,w in zip(linear,(.2126,.7152,.0722)))


def contrast(a,b):
    bright,dark = sorted([luminance(a),luminance(b)],reverse=True)
    return (bright+.05)/(dark+.05)


@pytest.mark.parametrize('kind,color,label', [
    ('DIRECT','#16A34A','Observado'), ('DERIVED','#9333EA','Calculado'),
    ('ENRICHED','#2563EB','Contextualizado')])
def test_central_colors_text_and_contrast(kind,color,label):
    style = PROVENANCE_STYLES[kind]
    assert style['color'] == color
    assert provenance_label(kind) == f'{kind} — {label}'
    badge = badge_html(kind)
    assert color in badge and label in badge and kind in badge
    # Badge/title foreground inherits theme; swatches and chart marks are graphical.
    assert 'color:inherit' in badge
    assert contrast(style['text'],color) >= 4.5
    assert contrast(color,'#0E1117') >= 3
    assert contrast(color,'#FFFFFF') >= 3


def test_table_style_preserves_exact_values_and_marks_only_requested_columns():
    table = pd.DataFrame({'period':['2026-01'], 'DIRECT':[str(2**60)], 'DERIVED':['100/3'],
                          'definition':['Definição externa']})
    original = table.copy(deep=True)
    styler = style_provenance_table(table, {'DIRECT':'DIRECT','DERIVED':'DERIVED'}, {(0,'definition')})
    styler._compute()
    for index, kind in [(1,'DIRECT'),(2,'DERIVED'),(3,'ENRICHED')]:
        assert ('background-color',PROVENANCE_STYLES[kind]['color']) in styler.ctx[(0,index)]
    assert not styler.ctx[(0,0)]
    pd.testing.assert_frame_equal(table,original)
    pd.testing.assert_frame_equal(styler.data,original)


@pytest.mark.parametrize('row', [
    {}, {'classification':'ENRICHED'}, {'definition':'texto'},
    {'definition':'texto','definition_source':' '},
    {'definition':'texto','definition_source':'SES-GO','conflict':True},
])
def test_no_enrichment_without_documented_source(row):
    assert not documented_enrichment(row)


def test_documented_definition_is_enriched_without_reclassifying_counts():
    row = {'definition':'Descrição documentada','definition_source':'SES-GO / BRImunobiologico',
           'count':50,'conflict':False}
    original = deepcopy(row)
    assert documented_enrichment(row)
    assert row == original


def test_chart_colors_preserve_numbers_gaps_and_sign():
    result = {'operation':'temporal','data':{'rows':[
        {'period':'2026-01','value':10,'metrics':{'delta_1':{'value':None}}},
        {'period':'2026-02','value':20,'metrics':{'delta_1':{'value':10}}},
        {'period':'2026-03','value':None,'metrics':{'delta_1':{'value':None}}},
        {'period':'2026-04','value':5,'metrics':{'delta_1':{'value':-15}}}]},'provenance':{}}
    original = deepcopy(result)
    direct = monthly_chart(result)
    derived = monthly_chart(result,'delta_1')
    assert direct.to_dict()['mark']['color'] == PROVENANCE_STYLES['DIRECT']['color']
    assert derived.to_dict()['mark']['color'] == PROVENANCE_STYLES['DERIVED']['color']
    assert derived.data['Valor'].tolist() == [10,-15]
    assert derived.data['Trecho'].nunique() == 2
    assert derived.data['Direção'].tolist() == ['Aumento','Redução']
    assert all('DERIVED — Calculado' == value for value in derived.data['Origem'])
    assert result == original


def test_app_legend_is_reusable_and_does_not_claim_external_context(monkeypatch):
    import sus_explorer.service
    service = Mock()
    monkeypatch.setattr(sus_explorer.service,'SUSExplorer',lambda:service)
    payload={'result':{'operation':'group','data':{'rows':[{'count':10,'value':'RS'}]},'provenance':{}},'answer':'Resultado'}
    original=deepcopy(payload)
    at=AppTest.from_file(APP)
    at.session_state['query_result']=payload
    at.run()
    assert not at.exception
    legends=[m.value for m in at.markdown if 'Legenda de proveniência' in m.value]
    assert len(legends)==1
    assert all(provenance_label(kind) in legends[0] for kind in PROVENANCE_STYLES)
    # ENRICHED appears only in legend, not as an actual result badge.
    assert not [m for m in at.markdown if 'ENRICHED — Contextualizado' in m.value and 'Legenda de proveniência' not in m.value]
    at.run()
    assert not at.exception
    service.ask.assert_not_called()
    assert at.session_state['query_result']==original


def test_group_definition_badge_requires_external_source():
    for source,expected in [(None,False),('SES-GO / BRImunobiologico',True)]:
        payload={'result':{'operation':'group','data':{'rows':[{'count':10,'value':'INF3',
            'definition':'Descrição','definition_source':source}]},'provenance':{}},'answer':'Resultado'}
        at=AppTest.from_file(APP)
        at.session_state['query_result']=payload
        at.run()
        assert not at.exception
        badges=[m for m in at.markdown if 'ENRICHED — Contextualizado' in m.value and 'Legenda de proveniência' not in m.value]
        assert bool(badges)==expected


def test_brand_hex_literals_live_only_in_presentation_configuration():
    root=Path(__file__).resolve().parents[2]
    files=[root/'sus_explorer'/'streamlit_views.py',root/'app.py']
    for path in files:
        assert not re.search(r'#(?:16A34A|9333EA|2563EB)',path.read_text(),re.I)


def test_dark_theme_uses_native_foreground_and_scoped_accents(monkeypatch):
    from streamlit import config
    original = config.get_option
    monkeypatch.setattr(config,'get_option',lambda key: 'dark' if key == 'theme.base' else original(key))
    at = AppTest.from_file(APP)
    at.session_state['query_result']={'result':{'operation':'latency',
        'data':{'median_days':2,'p90_days':4,'p95_days':5},'provenance':{}},'answer':'Resumo'}
    at.run()
    assert not at.exception
    assert all('DERIVED — Calculado' in metric.label for metric in at.metric)
    css = '\n'.join(m.value for m in at.markdown if '<style>' in m.value)
    assert 'st-key-sus_prov_DERIVED_' in css
    assert PROVENANCE_STYLES['DERIVED']['color'] in css
    assert 'color:' not in css.replace('border-left:', '')  # native theme text remains intact
