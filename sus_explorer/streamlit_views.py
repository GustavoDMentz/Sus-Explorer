"""Presentation of aggregate results only; no query or analytics calculations."""
from decimal import Decimal, InvalidOperation, localcontext
import math
import json
from fractions import Fraction
from copy import deepcopy

import altair as alt
import pandas as pd
import streamlit as st


LABELS = {1: 'Variação mensal', 2: 'Mudança na variação mensal',
          3: 'Mudança na segunda diferença'}


def chart_number(value):
    """Only plot numbers that survive browser representation without silent loss."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if abs(value) <= 2**53 - 1 else None
    try:
        exact = Decimal(str(value))
        number = float(exact)
        return number if math.isfinite(number) and Decimal(str(number)) == exact else None
    except (InvalidOperation, ValueError, OverflowError):
        return None


def calendar_rows(result):
    """Presentation-only placeholders; never alter or impute source observations."""
    rows = result.get('data', {}).get('rows', [])
    if not rows or result.get('operation') == 'temporal':
        return rows
    periods = [pd.Period(row['period'], freq='M') for row in rows]
    if periods != sorted(set(periods)):
        raise ValueError('monthly periods must be ordered and unique')
    by_period = {row['period']: row for row in rows}
    return [by_period.get(str(period), {'period': str(period), 'doses': None})
            for period in pd.period_range(periods[0], periods[-1], freq='M')]


def monthly_table(result):
    temporal = result.get('operation') == 'temporal'
    records = []
    for row in calendar_rows(result):
        record = {'Período': row['period'], 'Doses/registros (DIRECT)':
                  str(row.get('value' if temporal else 'doses')) if row.get('value' if temporal else 'doses') is not None else '—'}
        for key, metric in row.get('metrics', {}).items():
            record[f'{key} (DERIVED)'] = str(metric['value']) if metric['value'] is not None else '—'
            record[f'Razão ({key})'] = '; '.join(
                f"{reason['code']} ({reason['period']})" for reason in metric.get('unavailable_reasons', []))
        records.append(record)
    return pd.DataFrame(records)


MONTHS = ('jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez')


def month_label(period):
    return f"{MONTHS[int(period[5:7])-1]}/{period[2:4]}"


def percent_display(value):
    ratio = Fraction(value)
    with localcontext() as context:
        context.prec = max(40, len(str(abs(ratio.numerator))) + len(str(ratio.denominator)) + 4)
        return f"{Decimal(ratio.numerator) / Decimal(ratio.denominator):.2f}"


def monthly_chart(result, key=None):
    """Calendar spacing, bounded tick labels and explicit gap-separated segments."""
    rows = calendar_rows(result)
    records, segment, previous = [], 0, None
    for row in rows:
        period = pd.Period(row['period'], freq='M')
        metric = row.get('metrics', {}).get(key, {}) if key else {}
        value = metric.get('value') if key else row.get('value' if result['operation'] == 'temporal' else 'doses')
        # Percent plotting is a rounded presentation of an exact rational backend value.
        if key == 'pct_change' and value is not None:
            try:
                number = float(Fraction(value))
                number = number if math.isfinite(number) else None
            except OverflowError:
                number = None
        else:
            number = chart_number(value)
        if previous is not None and period.ordinal != previous.ordinal + 1:
            segment += 1
        if number is None:
            segment += 1
        else:
            records.append({'Período': period.to_timestamp(), 'Mês': month_label(row['period']),
                            'Valor': number, 'Exato': str(value), 'Trecho': str(segment),
                            'Unidade': '%' if key == 'pct_change' else result.get('provenance', {}).get('units', {}).get(key, 'doses/registros'),
                            'Origem': 'DERIVED' if key else 'DIRECT',
                            'Referência': result.get('provenance', {}).get('source_series_ref', 'Série agregada de origem'),
                            'Diferença absoluta': str(metric.get('absolute_change', row.get('metrics', {}).get('delta_1', {}).get('value', '—')))})
        previous = period
    if not records:
        return None
    frame = pd.DataFrame(records)
    chart = alt.Chart(frame)
    if key:
        chart = chart.mark_bar(size=18).encode(color=alt.condition('datum.Valor >= 0', alt.value('#178579'), alt.value('#c45656')))
    else:
        chart = chart.mark_line(point=alt.OverlayMarkDef(size=65), color='#2878a8')
    chart = chart.encode(
        x=alt.X('Período:T', title=None, scale=alt.Scale(domain=[pd.Period(rows[0]['period'],freq='M').to_timestamp().isoformat(),pd.Period(rows[-1]['period'],freq='M').to_timestamp().isoformat()]), axis=alt.Axis(values=[pd.Period(r['period'],freq='M').to_timestamp() for r in rows[::max(1, math.ceil(len(rows)/8))]], labelAngle=0, labelExpr="['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'][month(datum.value)] + '/' + timeFormat(datum.value, '%y')")),
        y=alt.Y('Valor:Q', title='Variação (%)' if key == 'pct_change' else result.get('provenance', {}).get('units', {}).get(key, 'Doses/registros'), scale=alt.Scale(zero=True), axis=alt.Axis(grid=True, labelFontSize=12)),
        detail='Trecho:N', tooltip=['Mês:N', alt.Tooltip('Valor:Q', format='.2f'), 'Exato:N', 'Unidade:N', 'Origem:N', 'Referência:N', 'Diferença absoluta:N'],
    ).properties(height=340).configure_axis(labelFontSize=12, titleFontSize=13).configure_view(stroke=None)
    return chart


def percentage_summary(rows):
    available = [(row['period'], Fraction(row['metrics']['pct_change']['value'])) for row in rows
                 if row.get('metrics', {}).get('pct_change', {}).get('value') is not None]
    phrases = []
    for period, value in available[-2:]:
        action = 'aumentou' if value > 0 else 'diminuiu' if value < 0 else 'não mudou'
        previous = str(pd.Period(period, freq='M') - 1)
        phrases.append(f"Em {month_label(period)}, o volume {action}" +
                       (f" {percent_display(abs(value))}%" if value else ' (0%)') +
                       f" em relação a {month_label(previous)}.")
    return ' '.join(phrases) or 'Não há pares mensais consecutivos com variação percentual calculável.'


def render_result(payload, question=''):
    result = deepcopy(payload.get('result') or {})
    if result.get('operation') == 'timeseries':
        result['data']['rows'] = calendar_rows(result)
    operation = result.get('operation')
    data, provenance = result.get('data', {}), result.get('provenance', {})
    origin = provenance.get('source_provenance', provenance)
    if operation in ('timeseries', 'temporal') and data.get('rows'):
        rows = data['rows']
        st.subheader(question or 'Análise mensal')
        st.caption(f"{month_label(rows[0]['period'])} — {month_label(rows[-1]['period'])} · Doses/registros, não pessoas vacinadas")
        observed = [r for r in rows if r.get('value' if operation == 'temporal' else 'doses') is not None]
        cards = st.columns(3)
        cards[0].metric('Meses com observações', len(observed))
        cards[1].metric('Meses indisponíveis', len(rows)-len(observed))
        latest = observed[-1] if observed else None
        cards[2].metric('Último volume mensal · DIRECT', f"{int(latest.get('value' if operation == 'temporal' else 'doses')):,}".replace(',', '.') if latest and isinstance(latest.get('value' if operation == 'temporal' else 'doses'), int) else str(latest.get('value' if operation == 'temporal' else 'doses')) if latest else '—')
        st.subheader('Doses/registros por mês · DIRECT')
        chart = monthly_chart(result)
        if chart is not None:
            st.altair_chart(chart, width='stretch')
        if operation == 'temporal':
            order = provenance['order']
            percent_available = any('pct_change' in r.get('metrics', {}) for r in rows)
            selection = st.radio('Métrica derivada', ['Variação percentual', 'Diferença absoluta'], horizontal=True) if percent_available else 'Diferença absoluta'
            key = 'pct_change' if selection == 'Variação percentual' else f'delta_{order}'
            st.subheader(('Variação percentual mensal' if key == 'pct_change' else LABELS[order]) + ' · DERIVED')
            st.caption('100 × (atual − anterior) / anterior · %' if key == 'pct_change' else f"{provenance['formula']} · {provenance['units'][key]}")
            unavailable = [month_label(r['period']) for r in rows if r.get('metrics', {}).get(key, {}).get('value') is None]
            if unavailable:
                st.caption('Métrica indisponível: ' + ', '.join(unavailable))
            chart = monthly_chart(result, key)
            if chart is not None:
                baseline = alt.Chart(pd.DataFrame({'zero': [0]})).mark_rule(color='#67717a').encode(y='zero:Q')
                base = chart.copy()
                base.config = alt.Undefined
                st.altair_chart((base + baseline).configure_axis(labelFontSize=12, titleFontSize=13).configure_view(stroke=None), width='stretch')
            else:
                st.info('Não há diferenças disponíveis para o intervalo consultado.')
            st.caption('Uma segunda diferença negativa pode representar crescimento ainda positivo, porém desacelerando. Diferenças finitas não demonstram causalidade ou inflexão confirmada.')
        missing_observations = [month_label(r['period']) for r in rows if r.get('value' if operation == 'temporal' else 'doses') is None]
        if missing_observations:
            st.info('Observações indisponíveis: ' + ', '.join(missing_observations))
        st.caption('Meses ausentes e diferenças indisponíveis não são zero. Os gráficos não conectam lacunas. Valores que não podem ser representados com segurança no navegador ficam apenas na tabela exata.')
        table = monthly_table(result)
        with st.expander('Tabela mensal · valores exatos e motivos de indisponibilidade'):
            st.dataframe(table, hide_index=True, width='stretch')
        st.download_button('Baixar tabela CSV', table.to_csv(index=False).encode('utf-8-sig'),
                           'sus_explorer_mensal.csv', 'text/csv', on_click='ignore')
    elif operation == 'count':
        st.metric('Doses/registros', str(data.get('doses', '—')))
    elif operation == 'group' and data.get('rows'):
        rows = data['rows']
        table = pd.DataFrame(rows)
        labels = [str(row.get('official_display') or row.get('value') or row.get('code') or row.get('display') or '—') for row in rows]
        frame = pd.DataFrame({'Grupo': labels, 'Doses/registros': [chart_number(row['count']) for row in rows]})
        st.altair_chart(alt.Chart(frame).mark_bar().encode(
            x='Doses/registros:Q', y=alt.Y('Grupo:N', sort='-x'), tooltip=['Grupo', 'Doses/registros']), width='stretch')
        st.dataframe(table.astype(str), hide_index=True, width='stretch')
    elif operation == 'latency':
        st.subheader('Latência operacional · dias')
        columns = st.columns(3)
        for column, key, label in zip(columns, ('median_days', 'p90_days', 'p95_days'),
                                      ('Mediana', 'P90', 'P95')):
            value = data.get(key)
            column.metric(label, str(value) if value is not None else '—')
        st.caption(f"Registros válidos: {data.get('n_valid', '—')}")
    st.subheader('Interpretação')
    st.write(percentage_summary(data['rows']) if operation == 'temporal' and any('pct_change' in r.get('metrics', {}) for r in data.get('rows', [])) else payload.get('answer') or 'Nenhuma interpretação disponível.')
    if operation == 'temporal' and provenance.get('order', 1) > 1:
        order = provenance['order']
        available = [(r['period'], r['metrics'][f'delta_{order}']['value']) for r in data['rows']
                     if r['metrics'][f'delta_{order}']['value'] is not None]
        if available:
            period, value = available[-1]
            sign = Decimal(str(value))
            action = 'aumentando' if sign > 0 else 'diminuindo' if sign < 0 else 'inalterada'
            subject = 'A variação mensal' if order == 2 else 'A segunda diferença'
            st.write(f"{subject} está {action} em {month_label(period)}: {value} {provenance['units'][f'delta_{order}']}.")
    if operation == 'temporal':
        st.caption('Percentuais descrevem variação do volume de doses; não são pontos percentuais, cobertura ou evidência de significância estatística.')
    for warning in result.get('warnings', []):
        st.warning(warning)
    st.download_button('Baixar resultado e proveniência JSON', json.dumps(payload, ensure_ascii=False, indent=2),
                       'sus_explorer_resultado.json', 'application/json', on_click='ignore')
    with st.expander('Plano, resultado e proveniência verificável'):
        st.caption(f"Operação: {operation} · Fragmentos: {origin.get('parquet_fragments', '—')} · Tempo de origem: {origin.get('elapsed_seconds', '—')} s")
        st.json(payload.get('plan', {}))
        st.json(result)
