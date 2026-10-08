from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from sus_explorer.analytics.campaigns import (load_catalog, compare_campaigns,
    CampaignCatalog, VerifiedCampaignSeries, common_complete_months, official_url)
from sus_explorer.analytics.temporal_query import FILTER_FIELDS
from sus_explorer.schemas import QueryPlan
from sus_explorer.streamlit_campaigns import campaign_chart

APP = str(Path(__file__).resolve().parents[2] / 'app.py')


@pytest.fixture(autouse=True)
def isolate_resource_cache():
    import streamlit as st
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def plan(**changes):
    return QueryPlan.model_validate({'operation': 'timeseries', 'uf': 'RS',
        'vaccine_text': 'influenza', 'start_year': 2026, 'start_month': 1,
        'end_year': 2026, 'end_month': 3} | changes)


def series(p=None, mode='daily', values=None):
    p = p or plan()
    data = []
    for c in load_catalog().campaigns:
        rows = [{'period': (c.start + timedelta(days=i)).isoformat(), 'doses': v}
                for i, v in enumerate(values if values is not None else [1] * 30)] if mode == 'daily' else [
                    {'period': f'{c.start.year}-05', 'doses': (values or [10])[0]}]
        data.append({'campaign_id': c.id, 'classification': 'DIRECT', 'granularity': mode,
            'date_basis': 'vaccination_date' if mode == 'daily' else 'vaccination_month',
            'geographic_basis': 'occurrence', 'filters': {f: getattr(p, f) for f in FILTER_FIELDS},
            'coverage_verified': True, 'campaign_scope_verified': True,
            'verification_source': c.source.url, 'recording_system': c.recording_requirement, 'rows': rows})
    return data


def run(p=None, **options):
    return compare_campaigns(p or plan(), [c.id for c in load_catalog().campaigns], **options).model_dump()


def codes(result):
    return {reason['code'] for reason in result['data']['unavailable_reasons']}


def test_verified_catalog_dates_scope_publication_and_candidate_month():
    catalog = load_catalog()
    assert catalog.catalog_version == '2026-10-08.1'
    assert [(str(c.start), str(c.end)) for c in catalog.campaigns] == [
        ('2023-04-10', '2023-05-31'), ('2024-03-25', '2024-05-31')]
    assert common_complete_months(catalog.campaigns) == [5]
    assert catalog.campaigns[0].source.publication_date is None
    assert 'sem data de publicação' in catalog.campaigns[0].source.publication_date_note
    assert str(catalog.campaigns[1].source.publication_date) == '2024-03-16'
    assert all(c.applicable_ufs == ['RS'] for c in catalog.campaigns)
    assert 'consolidado' in catalog.campaigns[0].source.recording_locator


@pytest.mark.parametrize('url', ['https://example.com/ms', 'https://www.gov.br.evil/saude/x',
    'http://www.gov.br/saude/x', 'https://www.gov.br/other/x', 'https://user@www.gov.br/saude/x'])
def test_unofficial_source_urls_rejected(url):
    with pytest.raises(ValueError):
        official_url(url)


def test_catalog_rejects_duplicates_reversed_dates_and_unverified_scope():
    original = load_catalog().model_dump(mode='json')
    for mutate in [lambda x: x['campaigns'][1].update(id=x['campaigns'][0]['id']),
                   lambda x: x['campaigns'][0].update(end='2023-01-01'),
                   lambda x: x['campaigns'][0].update(applicable_ufs=['SC'])]:
        payload = deepcopy(original)
        mutate(payload)
        with pytest.raises(ValueError):
            CampaignCatalog.model_validate(payload)


@pytest.mark.parametrize('mode', ['daily', 'monthly'])
def test_current_backend_is_unavailable_even_when_calendar_has_common_month(mode):
    p = plan(municipality_code='4314902', age_min=60, sex='F')
    original = p.model_dump()
    result = run(p, mode=mode)
    assert result['data']['status'] == 'unavailable'
    assert result['data']['rows'] == [] and result['data']['comparison'] == []
    assert 'CONSOLIDATED_CAMPAIGN_NOT_RECONCILED' in codes(result)
    assert 'NO_VERIFIED_CAMPAIGN_EXTRACT' in codes(result)
    assert campaign_chart(result) is None
    assert p.model_dump() == original
    assert result['provenance']['filters']['municipality_code'] == '4314902'
    assert result['provenance']['catalog_ref'].startswith('campaign-catalog:sha256:')


def test_sixty_days_not_silently_shortened_to_fit_2023():
    assert 'WINDOW_EXCEEDS_DOCUMENTED_PERIOD' in codes(run(window_days=60))
    assert run(window_days=60)['provenance']['window_days'] == 60


@pytest.mark.parametrize('changes,code', [({'uf': 'SC'}, 'UNSUPPORTED_GEOGRAPHY'),
    ({'vaccine_text': 'covid'}, 'UNVERIFIED_IMMUNOBIOLOGICAL'),
    ({'vaccine_text': None, 'vaccine_code': '33'}, 'UNVERIFIED_IMMUNOBIOLOGICAL'),
    ({'day': 1}, 'UNSUPPORTED_FILTER')])
def test_unsupported_scope_does_not_silently_rewrite_filters(changes, code):
    assert code in codes(run(plan(**changes)))


def test_daily_accumulated_comparison_aligns_elapsed_day_preserves_exact_observations():
    p = plan(municipality_code='4314902', vaccine_code='33', age_min=60, age_max=80, sex='F')
    observed = series(p, values=[1] * 30)
    observed[1]['rows'] = [r | {'doses': 2} for r in observed[1]['rows']]
    original = deepcopy(observed)
    result = run(p, series=observed)
    assert [r['difference'] for r in result['data']['comparison']] == list(range(1, 31))
    assert result['data']['rows'][0]['period'] == '2023-04-10'
    assert result['data']['rows'][30]['period'] == '2024-03-25'
    assert observed == original
    assert result['provenance']['calendar_classification'] == 'ENRICHED'
    assert result['data']['rows'][0]['observed_classification'] == 'DIRECT'
    assert result['data']['rows'][0]['cumulative_classification'] == 'DERIVED'
    chart = campaign_chart(result)
    assert len(chart.data) == 60 and chart.data['Posição'].max() == 30
    chart.to_dict()


@pytest.mark.parametrize('null', [False, True])
def test_sparse_or_null_days_stop_accumulation_and_both_lines_at_common_prefix(null):
    observed = series()
    if null:
        observed[0]['rows'][3]['doses'] = None
    else:
        del observed[0]['rows'][3]
    result = run(series=observed)
    assert result['data']['rows'][3]['observed_doses'] is None
    assert all(r['cumulative_doses'] is None for r in result['data']['rows'][3:30])
    assert all(r['difference'] is None for r in result['data']['comparison'][3:])
    chart = campaign_chart(result)
    assert chart.data['Posição'].max() == 3 and len(chart.data) == 6


def test_observed_zero_is_valid_but_empty_series_never_becomes_zero():
    result = run(series=series(values=[0] * 30))
    assert all(r['difference'] == 0 for r in result['data']['comparison'])
    empty = series(values=[])
    result = run(series=empty)
    assert all(r['difference'] is None for r in result['data']['comparison'])
    assert campaign_chart(result) is None


def test_monthly_approximation_never_allocates_doses_to_days():
    result = run(mode='monthly', series=series(mode='monthly'))
    assert [r['period'] for r in result['data']['rows']] == ['2023-05', '2024-05']
    assert all(r['elapsed_day'] is None for r in result['data']['rows'])
    assert result['provenance']['approximation'] is True
    assert result['provenance']['window_days'] is None
    assert result['data']['comparison'][0]['difference'] == 0
    campaign_chart(result).to_dict()


def test_decline_is_descriptive_and_partial_window_is_explicit():
    observed = series()
    observed[0]['rows'] = [row | {'doses': 2} for row in observed[0]['rows']]
    result = run(series=observed)
    assert result['data']['comparison'][-1]['difference'] == -30
    assert result['data']['window_complete'] is True
    assert result['data']['comparable_periods'] == 30
    del observed[0]['rows'][2]
    result = run(series=observed)
    assert result['data']['window_complete'] is False
    assert result['data']['comparable_periods'] == 2
    assert any('Janela incompleta' in w for w in result['warnings'])


@pytest.mark.parametrize('change,code', [({'date_basis': 'partition_month'}, 'INCOMPATIBLE_DATE_BASIS'),
    ({'coverage_verified': False}, 'UNVERIFIED_SOURCE_COVERAGE'),
    ({'campaign_scope_verified': False}, 'UNVERIFIED_SOURCE_COVERAGE'),
    ({'recording_system': 'microdata'}, 'INCOMPATIBLE_RECORDING_SYSTEM'),
    ({'geographic_basis': 'residence'}, 'INCONSISTENT_GEOGRAPHIC_BASIS')])
def test_unverified_extracts_cannot_enable_chart(change, code):
    observed = series()
    observed[0].update(change)
    result = run(series=observed)
    assert code in codes(result) and campaign_chart(result) is None


def test_filters_order_duplicates_and_outside_campaign_rejected():
    observed = series()
    observed[0]['filters']['municipality_code'] = '4300000'
    assert 'INCONSISTENT_FILTERS' in codes(run(series=observed))
    for rows in [series()[0]['rows'][::-1], series()[0]['rows'] * 2,
                 [{'period': '2023-01-01', 'doses': 1}]]:
        observed = series()
        observed[0]['rows'] = rows
        with pytest.raises(ValueError):
            run(series=observed)


def test_large_counts_preserved_and_microdata_fields_rejected():
    observed = series(values=[2**60] * 30)
    result = run(series=observed)
    assert result['data']['rows'][29]['cumulative_doses'] == 30 * 2**60
    assert campaign_chart(result) is None
    observed[0]['rows'][0]['patient_id'] = 'never allowed'
    with pytest.raises(ValueError):
        VerifiedCampaignSeries.model_validate(observed[0])


def test_section_has_clickable_official_sources_no_queries_and_original_payload_preserved(monkeypatch):
    import sus_explorer.service
    service = Mock()
    monkeypatch.setattr(sus_explorer.service, 'SUSExplorer', lambda: service)
    payload = {'plan': plan().model_dump(), 'result': {'operation': 'timeseries',
        'data': {'rows': [{'period': '2026-01', 'doses': 10}, {'period': '2026-02', 'doses': 20}]},
        'provenance': {}}, 'answer': 'Resumo'}
    original = deepcopy(payload)
    at = AppTest.from_file(APP)
    at.session_state['query_result'] = payload
    at.run()
    assert not at.exception
    assert any(s.value == 'Comparação entre campanhas oficiais' for s in at.subheader)
    links = '\n'.join(m.value for m in at.markdown)
    assert all(c.source.url in links for c in load_catalog().campaigns)
    assert any('Nenhum volume foi estimado' in i.value for i in at.info)
    radio = next(r for r in at.radio if r.label == 'Janela de campanha')
    radio.set_value('Aproximação mensal — meses completos comuns').run()
    assert not at.exception
    assert any('MONTHLY_APPROXIMATION_NOT_VALIDATED' in c.value for c in at.caption)
    service.ask.assert_not_called()
    service.pni.execute.assert_not_called()
    assert at.session_state['query_result'] == original
