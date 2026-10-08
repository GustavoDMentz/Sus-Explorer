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
    result.provenance['percentage_change'] = {
        'classification': 'DERIVED', 'formula': '100 * (y(t) - y(t-1)) / y(t-1)',
        'method_version': '1.0.0', 'unit': '%', 'numeric_encoding': 'exact rational string',
        'missing_policy': 'null_no_gap_crossing', 'zero_denominator_policy': 'null',
        'source_series_ref': result.provenance['source_series_ref'],
    }
