"""Exact calendar-aligned YoY metrics, independent of monthly finite differences."""
from fractions import Fraction
from .temporal import _month, _period, _difference


def add_yoy(result, history, main_query, reference_query):
    if any(reference_query[name] != main_query[name] - (1 if name.endswith('year') else 0)
           for name in ('start_year', 'start_month', 'end_year', 'end_month')):
        raise ValueError('Reference period must be exactly one calendar year earlier')
    if main_query['filters'] != reference_query['filters']:
        raise ValueError('YoY requires identical filters')
    if history.provenance.get('source_provenance', {}).get('uf_partition', main_query['filters']['uf']) != main_query['filters']['uf']:
        raise ValueError('Reference UF mismatch')
    main_filter = result.provenance.get('source_provenance', {}).get('vaccine_filter')
    historical_filter = history.provenance.get('source_provenance', {}).get('vaccine_filter')
    if any(row['observation_status'] == 'OBSERVED' for row in history.data['rows']) and main_filter != historical_filter:
        raise ValueError('Resolved vaccine filters must match')
    indexed = {row['period']: row for row in history.data['rows']}
    for row in result.data['rows']:
        reference_period = _period(_month(row['period']) - 12)
        reference = indexed.get(reference_period)
        previous = reference['value'] if reference else None
        reasons = []
        if row['value'] is None:
            reasons.append({'code': row['observation_status'], 'period': row['period']})
        if previous is None:
            reasons.append({'code': 'MISSING_REFERENCE_MONTH' if reference is None or reference['observation_status'] == 'MISSING_MONTH'
                            else 'MISSING_REFERENCE_VALUE', 'period': reference_period})
        delta = None if reasons else _difference([row['value'], previous], 1)
        pct_reasons = list(reasons)
        if previous == 0:
            pct_reasons.append({'code': 'ZERO_DENOMINATOR', 'period': reference_period})
        pct = None if pct_reasons else str(100 * Fraction(delta) / Fraction(previous))
        common = {'classification': 'DERIVED', 'reference_period': reference_period, 'reference_value': previous}
        row['metrics']['yoy_delta'] = common | {'value': delta, 'unit': 'doses', 'unavailable_reasons': reasons}
        row['metrics']['yoy_pct'] = common | {'value': pct, 'unit': '%', 'unavailable_reasons': pct_reasons}
    result.provenance['yoy'] = {
        'classification': 'DERIVED', 'method': 'same_calendar_month_previous_year', 'method_version': '1.0.0',
        'formulas': {'yoy_delta': 'y(t) - y(t-12)', 'yoy_pct': '100 * (y(t) - y(t-12)) / y(t-12)'},
        'units': {'yoy_delta': 'doses', 'yoy_pct': '%'}, 'lag_months': 12,
        'numeric_encoding': 'yoy_delta int or exact Decimal string; yoy_pct exact rational string',
        'zero_denominator_policy': 'null_percentage_only',
        'reference_query': reference_query, 'reference_period': history.provenance['period'],
        'reference_series_ref': history.provenance['source_series_ref'],
        'reference_provenance': history.provenance['source_provenance'],
        'main_series_ref': result.provenance['source_series_ref'], 'missing_policy': 'null_no_reference_imputation',
    }
    result.warnings.append('YoY compara o mesmo mês do ano anterior; não elimina efeitos de calendário, disponibilidade de dados ou população-alvo, nem confirma causalidade ou anomalias.')
