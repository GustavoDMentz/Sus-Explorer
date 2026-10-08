"""Official calendar snapshots and guarded, aggregate-only campaign comparisons.

The current partition-month backend cannot provide verified campaign extracts.
Calendar evidence alone never authorizes treating those counts as campaign totals.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..schemas import QueryPlan
from .temporal import TemporalAnalyticsResult
from .temporal_query import FILTER_FIELDS

CATALOG_PATH = Path(__file__).with_name('campaign_catalog.json')


def official_url(value: str) -> str:
    url = urlsplit(value)
    if (url.scheme != 'https' or url.netloc != 'www.gov.br' or
            not url.path.startswith('/saude/') or url.query or url.fragment):
        raise ValueError('Campaign evidence must be an official Ministry of Health URL')
    return value


class CatalogSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    publisher: Literal['Ministério da Saúde']
    title: str = Field(min_length=1)
    url: str
    metadata_url: str
    publication_date: date | None
    publication_date_note: str = Field(min_length=1)
    page_updated_on: date | None
    edition: str | None
    calendar_locator: str = Field(min_length=1)
    recording_locator: str = Field(min_length=1)

    @model_validator(mode='after')
    def validate_urls(self):
        official_url(self.url)
        official_url(self.metadata_url)
        return self


class OfficialCampaign(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    immunobiological: Literal['influenza']
    start: date
    end: date
    date_status: Literal['planned_in_cited_document']
    geographic_scope: str = Field(min_length=1)
    applicable_ufs: list[Literal['RS']]
    recording_requirement: Literal['consolidated_campaign_module', 'verified_campaign_extract']
    source: CatalogSource

    @model_validator(mode='after')
    def validate_bounds(self):
        if self.start > self.end or self.start.year != self.end.year or self.applicable_ufs != ['RS']:
            raise ValueError('Invalid campaign calendar or MVP scope')
        return self


class CampaignCatalog(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['1.0.0']
    catalog_version: str = Field(min_length=1)
    verified_on: date
    scope: str = Field(min_length=1)
    campaigns: list[OfficialCampaign] = Field(min_length=2)

    @model_validator(mode='after')
    def validate_ids(self):
        if len({c.id for c in self.campaigns}) != len(self.campaigns):
            raise ValueError('Duplicate campaign identifiers')
        return self


def load_catalog(path=CATALOG_PATH):
    return CampaignCatalog.model_validate_json(Path(path).read_text(encoding='utf-8'))


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return sha256(raw.encode('utf-8')).hexdigest()


class CampaignObservation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    period: str
    doses: int | None = Field(strict=True, ge=0)


class VerifiedCampaignSeries(BaseModel):
    """Future adapter input; these attestations are absent from the current backend.

    Completeness/scope attestations require an official extract and an audit, not
    merely nonempty rows or a present partition. No adapter is fabricated here.
    """
    model_config = ConfigDict(extra='forbid')
    campaign_id: str
    classification: Literal['DIRECT']
    granularity: Literal['daily', 'monthly']
    date_basis: Literal['vaccination_date', 'vaccination_month', 'partition_month']
    geographic_basis: Literal['occurrence', 'residence']
    filters: dict
    coverage_verified: bool = Field(strict=True)
    campaign_scope_verified: bool = Field(strict=True)
    verification_source: str
    recording_system: Literal['consolidated_campaign_module', 'verified_campaign_extract', 'microdata']
    rows: list[CampaignObservation]

    @model_validator(mode='after')
    def validate_evidence(self):
        official_url(self.verification_source)
        if set(self.filters) != set(FILTER_FIELDS):
            raise ValueError('All applicable filters must be explicit')
        periods = [row.period for row in self.rows]
        if periods != sorted(set(periods)):
            raise ValueError('Campaign periods must be ordered and unique')
        return self


def common_complete_months(campaigns):
    """Calendar-month approximation, never fake elapsed-day alignment."""
    return [month for month in range(1, 13) if all(
        c.start <= date(c.start.year, month, 1) and
        date(c.start.year, month, monthrange(c.start.year, month)[1]) <= c.end
        for c in campaigns)]


def compare_campaigns(plan, campaign_ids, *, mode='daily', window_days=30, series=None, catalog=None):
    """Independent result. Without adequate supplied extracts, return no volumes.

    Current Streamlit calls this with series=None: no network, source queries,
    implicit interval extensions, or conversion of partition months into days.
    """
    plan = QueryPlan.model_validate(plan.model_dump() if isinstance(plan, QueryPlan) else plan)
    catalog = catalog or load_catalog()
    if mode not in ('daily', 'monthly') or type(window_days) is not int or window_days not in (30, 60):
        raise ValueError('Choose daily/monthly and a 30/60-day window')
    if len(campaign_ids) != 2 or len(set(campaign_ids)) != 2:
        raise ValueError('Choose two distinct official campaigns')
    by_id = {c.id: c for c in catalog.campaigns}
    if any(key not in by_id for key in campaign_ids):
        raise ValueError('Unknown official campaign')
    campaigns = sorted([by_id[key] for key in campaign_ids], key=lambda c: c.start)
    filters = {key: getattr(plan, key) for key in FILTER_FIELDS}
    reasons = []

    def unavailable(code, message, campaign_id=None):
        reasons.append({'code': code, 'message': message, 'campaign_id': campaign_id})

    if plan.uf != 'RS':
        unavailable('UNSUPPORTED_GEOGRAPHY', 'O catálogo MVP cobre somente influenza no RS.')
    # Text is explicit; a code-only request needs verified resolution in an adapter.
    if not plan.vaccine_text or plan.vaccine_text.strip().casefold() not in (
            'influenza', 'influenza trivalente', 'influenza tetravalente'):
        unavailable('UNVERIFIED_IMMUNOBIOLOGICAL', 'Informe um filtro explícito de influenza; códigos isolados precisam de resolução verificada.')
    if plan.day is not None or plan.group_by is not None:
        unavailable('UNSUPPORTED_FILTER', 'Filtros de dia ou agrupamento não podem ser descartados na comparação.')
    months = common_complete_months(campaigns)
    if mode == 'daily':
        for c in campaigns:
            if c.start + timedelta(days=window_days - 1) > c.end:
                unavailable('WINDOW_EXCEEDS_DOCUMENTED_PERIOD', f'A janela de {window_days} dias excede o calendário previsto no documento; não será encurtada silenciosamente.', c.id)
    elif not months:
        unavailable('NO_COMMON_COMPLETE_MONTH', 'Não há meses calendários inteiros comuns aos calendários citados.')
    dumped_catalog = catalog.model_dump(mode='json')
    provenance = {'classification': 'DERIVED', 'calendar_classification': 'ENRICHED',
        'source_classification': 'DIRECT', 'catalog_version': catalog.catalog_version,
        'catalog_ref': 'campaign-catalog:sha256:' + digest(dumped_catalog),
        'verified_on': catalog.verified_on.isoformat(), 'filters': filters,
        'mode': mode, 'window_days': window_days if mode == 'daily' else None,
        'date_basis': 'vaccination_date' if mode == 'daily' else 'vaccination_month',
        'approximation': mode == 'monthly', 'missing_policy': 'null; never zero; cumulative stops at first unavailable period',
        'campaigns': [c.model_dump(mode='json') for c in campaigns], 'source_refs': {},
        'formulas': {'cumulative': 'C(d) = sum(y(i), i=1..d), only if every preceding day is observed',
                     'comparison': 'C_later(d) - C_earlier(d)'}, 'unit': 'doses/registros',
        'microdata_sent_to_llm': False}
    warnings = ['Calendários previstos nos documentos citados; não comprovam início municipal efetivo nem todas as prorrogações.',
        'Diferenças não demonstram desempenho, cobertura, eficácia ou causalidade; públicos-alvo e sistemas de registro podem diferir.']
    if mode == 'monthly':
        provenance['formulas'] = {'cumulative': 'sum(y(month)) over selected complete calendar months only',
                                 'comparison': 'C_later(month) - C_earlier(month) over the same selected months'}
        warnings.append('Aproximação mensal por meses completos comuns; não representa os primeiros 30/60 dias, acumulados diários nem o total de cada campanha.')
    if series is None:
        unavailable('NO_VERIFIED_CAMPAIGN_EXTRACT', 'O backend atual conta partições mensais de microdados, sem reconciliação com os módulos oficiais das campanhas.')
        if mode == 'daily':
            unavailable('DAILY_DATA_UNAVAILABLE', 'Não há série diária por data de aplicação com completude verificada no contrato atual.')
        else:
            unavailable('MONTHLY_APPROXIMATION_NOT_VALIDATED', 'A existência de um mês completo no calendário não comprova a adequação dos microdados para comparar campanhas.')
        for c in campaigns:
            if c.recording_requirement == 'consolidated_campaign_module':
                unavailable('CONSOLIDATED_CAMPAIGN_NOT_RECONCILED', 'O informe exige registro consolidado no módulo da campanha; equivalência com os microdados não foi demonstrada.', c.id)
        return TemporalAnalyticsResult('campaign_comparison', {'status': 'unavailable', 'rows': [],
            'comparison': [], 'unavailable_reasons': reasons, 'candidate_months': months}, provenance, warnings)

    supplied = [VerifiedCampaignSeries.model_validate(s) for s in series]
    if {s.campaign_id for s in supplied} != set(campaign_ids) or len(supplied) != 2:
        raise ValueError('Exactly one verified series is required per campaign')
    if len({s.geographic_basis for s in supplied}) != 1:
        unavailable('INCONSISTENT_GEOGRAPHIC_BASIS', 'Não é possível misturar residência e ocorrência.')
    indexed = {}
    for source in supplied:
        c = by_id[source.campaign_id]
        if source.filters != filters:
            unavailable('INCONSISTENT_FILTERS', 'Os filtros de cada campanha devem ser idênticos aos solicitados.', c.id)
        if source.granularity != mode or source.date_basis != provenance['date_basis']:
            unavailable('INCOMPATIBLE_DATE_BASIS', 'Partição mensal não equivale à data de aplicação.', c.id)
        if not source.coverage_verified or not source.campaign_scope_verified:
            unavailable('UNVERIFIED_SOURCE_COVERAGE', 'A completude e a adequação da extração à campanha precisam de verificação documentada.', c.id)
        if source.recording_system != c.recording_requirement:
            unavailable('INCOMPATIBLE_RECORDING_SYSTEM', 'A extração deve respeitar o sistema de registro da campanha documentada.', c.id)
        provenance['source_refs'][c.id] = 'campaign-series:sha256:' + digest(source.model_dump(mode='json'))
        indexed[c.id] = {r.period: r.doses for r in source.rows}
        for period in indexed[c.id]:
            try:
                point = date.fromisoformat(period if mode == 'daily' else period + '-01')
                valid = (len(period) == (10 if mode == 'daily' else 7) and
                         (c.start <= point <= c.end if mode == 'daily' else point.month in months and point.year == c.start.year))
            except ValueError:
                valid = False
            if not valid:
                raise ValueError('Observation outside the documented campaign/calendar selection')
    if reasons:
        return TemporalAnalyticsResult('campaign_comparison', {'status': 'unavailable', 'rows': [],
            'comparison': [], 'unavailable_reasons': reasons, 'candidate_months': months}, provenance, warnings)

    rows, comparisons, values = [], [], {}
    for c in campaigns:
        accumulated, available = 0, True
        values[c.id] = []
        periods = [(c.start + timedelta(days=i)).isoformat() for i in range(window_days)] if mode == 'daily' else [f'{c.start.year}-{m:02d}' for m in months]
        for index, period in enumerate(periods, 1):
            observed = indexed[c.id].get(period)
            available = available and observed is not None
            if observed is not None:
                accumulated += observed
            value = accumulated if available else None
            values[c.id].append(value)
            rows.append({'campaign_id': c.id, 'campaign': c.title, 'period': period,
                'elapsed_day': index if mode == 'daily' else None,
                'observed_doses': observed, 'observed_classification': 'DIRECT',
                'cumulative_doses': value, 'cumulative_classification': 'DERIVED',
                'unavailable_reasons': [] if available else [{'code': 'INCOMPLETE_CUMULATIVE_WINDOW', 'period': period}]})
    earlier, later = campaigns
    for i, (a, b) in enumerate(zip(values[earlier.id], values[later.id]), 1):
        comparisons.append({'elapsed_day': i if mode == 'daily' else None,
            'calendar_month': months[i-1] if mode == 'monthly' else None,
            'difference': b - a if a is not None and b is not None else None, 'classification': 'DERIVED'})
    provenance['geographic_basis'] = supplied[0].geographic_basis
    if plan.vaccine_code:
        # A supplied extract must attest the code's campaign scope; never expand it.
        provenance['code_scope'] = 'verified_in_campaign_extract; filter preserved'
    comparable_periods = sum(row['difference'] is not None for row in comparisons)
    if comparable_periods != len(comparisons):
        warnings.append('Janela incompleta: somente o trecho inicial observado em ambas as campanhas pode ser comparado; sem completar ou extrapolar a janela solicitada.')
    return TemporalAnalyticsResult('campaign_comparison', {'status': 'ready', 'rows': rows,
        'comparison': comparisons, 'window_complete': comparable_periods == len(comparisons),
        'comparable_periods': comparable_periods, 'unavailable_reasons': [],
        'candidate_months': months}, provenance, warnings)
