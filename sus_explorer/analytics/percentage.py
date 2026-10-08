"""Exact monthly percentages, encoded as rational numbers (including repeating values)."""
from decimal import Decimal
from fractions import Fraction
from .temporal import _month


def percentage_changes(rows):
    output, previous, previous_month = [], None, None
    for row in rows:
        month = _month(row['period'])
        if previous_month is not None and month <= previous_month:
            raise ValueError('periods must be strictly ordered without duplicates')
        value = row['value']
        if value is not None and not (type(value) is int or isinstance(value, Decimal) and value.is_finite()):
            raise ValueError('values must be exact int, Decimal or None')
        reasons = []
        if value is None:
            reasons.append({'code': 'MISSING_MONTH' if row.get('observation_status') == 'MISSING_MONTH' else 'MISSING_VALUE', 'period': row['period']})
        if previous_month is None:
            reasons.append({'code': 'INSUFFICIENT_HISTORY', 'period': None})
        elif month != previous_month + 1:
            reasons.append({'code': 'MISSING_MONTH', 'period': row['period']})
        elif previous is None:
            prior = rows[len(output)-1]
            reasons.append({'code': 'MISSING_MONTH' if prior.get('observation_status') == 'MISSING_MONTH' else 'MISSING_VALUE', 'period': prior['period']})
        elif previous == 0:
            reasons.append({'code': 'ZERO_DENOMINATOR', 'period': rows[len(output)-1]['period']})
        ratio = None if reasons else 100 * (Fraction(value) - Fraction(previous)) / Fraction(previous)
        output.append({'classification': 'DERIVED', 'unit': '%',
                       'value': str(ratio) if ratio is not None else None,
                       'absolute_change': str(Fraction(value) - Fraction(previous)) if ratio is not None else None,
                       'unavailable_reasons': reasons})
        previous, previous_month = value, month
    return output


def add_percentages(result):
    rows = result.data['rows']
    for row, metric in zip(rows, percentage_changes(rows)):
        row['metrics']['pct_change'] = metric
    result.data['summary'] = summarize_series(rows)
    result.provenance['series_summary'] = {
        'classification': 'DERIVED', 'method': 'observed_monthly_series_summary',
        'method_version': '1.0.0', 'missing_policy': 'observed_only_no_gap_crossing',
        'source_series_ref': result.provenance['source_series_ref'],
    }
    result.provenance['percentage_change'] = {
        'classification': 'DERIVED', 'formula': '100 * (y(t) - y(t-1)) / y(t-1)',
        'method_version': '1.0.0', 'unit': '%', 'numeric_encoding': 'exact rational string',
        'missing_policy': 'null_no_gap_crossing', 'zero_denominator_policy': 'null',
        'source_series_ref': result.provenance['source_series_ref'],
    }


def summarize_series(rows):
    """Descriptive aggregates from observed months; no seasonal/causal inference.

    Reuse exact finite differences. Percentages retain their existing contract.
    Null months count as unavailable and never participate in transitions.
    """
    from .temporal import _difference
    percentages = percentage_changes(rows)  # also validates exact values/calendar order
    observed = [row for row in rows if row['value'] is not None]
    total = sum((Fraction(row['value']) for row in observed), Fraction(0)) if observed else None
    maximum = max((row['value'] for row in observed), default=None)
    minimum = min((row['value'] for row in observed), default=None)
    transitions = []
    for previous, current, percentage in zip(rows, rows[1:], percentages[1:]):
        if (_month(current['period']) != _month(previous['period']) + 1
                or previous['value'] is None or current['value'] is None):
            continue
        change = _difference([current['value'], previous['value']], 1)
        transitions.append({
            'from_period': previous['period'], 'period': current['period'],
            'previous_value': str(previous['value']), 'value': str(current['value']),
            'absolute_change': str(change), 'pct_change': percentage['value'],
        })
    greatest = max((abs(Fraction(t['absolute_change'])) for t in transitions), default=None)
    peaks = [row['period'] for row in observed if row['value'] == maximum]
    return {
        'classification': 'DERIVED', 'method': 'observed_monthly_series_summary',
        'method_version': '1.0.0', 'observed_total': str(total) if total is not None else None,
        'observed_months': len(observed), 'unavailable_months': len(rows) - len(observed),
        'total_is_partial': len(observed) != len(rows),
        'peak': {'value': str(maximum) if maximum is not None else None, 'periods': peaks},
        'minimum': {'value': str(minimum) if minimum is not None else None,
                    'periods': [row['period'] for row in observed if row['value'] == minimum]},
        'greatest_absolute_changes': [t for t in transitions if abs(Fraction(t['absolute_change'])) == greatest],
        'extreme_increases': [t for t in transitions if t['pct_change'] is not None and Fraction(t['pct_change']) > 100],
        'increases_before_last_peak': [t for t in transitions if peaks and t['period'] <= peaks[-1]
                                      and Fraction(t['absolute_change']) > 0],
        'declines_after_last_peak': [t for t in transitions if peaks and t['period'] > peaks[-1]
                                   and Fraction(t['absolute_change']) < 0],
    }
