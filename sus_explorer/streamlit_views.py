"""Presentation of aggregate results only; no query or analytics calculations."""
from decimal import Decimal, InvalidOperation, localcontext
import math
import json
from fractions import Fraction
from copy import deepcopy

import altair as alt
import pandas as pd
import streamlit as st

from .streamlit_provenance import (PROVENANCE_STYLES, NEUTRAL_REFERENCE,
    provenance_label, render_provenance_legend, install_provenance_styles,
    provenance_heading, provenance_metric, style_provenance_table, documented_enrichment, badge_html)


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


def monthly_chart(result, key=None, *, show_extreme=True):
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
        if key == 'pct_change' and not show_extreme and value is not None and Fraction(value) > 100:
            number = None
        if previous is not None and period.ordinal != previous.ordinal + 1:
            segment += 1
        if number is None:
            segment += 1
        else:
            records.append({'Período': period.to_timestamp(), 'Mês': month_label(row['period']),
                            'Valor': number, 'Exato': str(value), 'Trecho': str(segment),
                            'Unidade': '%' if key == 'pct_change' else result.get('provenance', {}).get('units', {}).get(key, 'doses/registros'),
                            'Origem': provenance_label('DERIVED' if key else 'DIRECT'),
                            'Direção': 'Aumento' if number > 0 else 'Redução' if number < 0 else 'Sem mudança',
                            'Referência': result.get('provenance', {}).get('source_series_ref', 'Série agregada de origem'),
                            'Diferença absoluta': str(metric.get('absolute_change', row.get('metrics', {}).get('delta_1', {}).get('value', '—')))})
        previous = period
    if not records:
        return None
    frame = pd.DataFrame(records)
    chart = alt.Chart(frame)
    if key:
        chart = chart.mark_bar(size=18, color=PROVENANCE_STYLES['DERIVED']['color'])
    else:
        chart = chart.mark_line(point=alt.OverlayMarkDef(size=65), color=PROVENANCE_STYLES['DIRECT']['color'])
    chart = chart.encode(
        x=alt.X('Período:T', title=None, scale=alt.Scale(domain=[pd.Period(rows[0]['period'],freq='M').to_timestamp().isoformat(),pd.Period(rows[-1]['period'],freq='M').to_timestamp().isoformat()]), axis=alt.Axis(values=[pd.Period(r['period'],freq='M').to_timestamp() for r in rows[::max(1, math.ceil(len(rows)/8))]], labelAngle=0, labelExpr="['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'][month(datum.value)] + '/' + timeFormat(datum.value, '%y')")),
        y=alt.Y('Valor:Q', title='Variação (%)' if key == 'pct_change' else result.get('provenance', {}).get('units', {}).get(key, 'Doses/registros'), scale=alt.Scale(zero=True), axis=alt.Axis(grid=True, labelFontSize=12)),
        detail='Trecho:N', tooltip=['Mês:N', alt.Tooltip('Valor:Q', format='.2f'), 'Exato:N', 'Unidade:N', 'Origem:N', 'Direção:N', 'Referência:N', 'Diferença absoluta:N'],
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


def dose_display(value):
    if value is None:
        return '—'
    exact = Fraction(value)
    if exact.denominator == 1:
        return f'{exact.numerator:,}'.replace(',', '.')
    with localcontext() as context:
        context.prec = max(40, len(str(abs(exact.numerator))) + len(str(exact.denominator)) + 4)
        decimal = Decimal(exact.numerator) / Decimal(exact.denominator)
        return format(decimal, 'f').rstrip('0').rstrip('.').replace('.', ',')


def contextual_summary(summary):
    if summary['observed_months'] == 0:
        return 'Não há volumes mensais observados para descrever o comportamento da série.'
    peak = summary['peak']
    periods = ', '.join(month_label(p) for p in peak['periods'])
    parts = [f"O maior volume mensal observado foi {dose_display(peak['value'])} doses/registros, em {periods}."]
    minimum = summary['minimum']
    if minimum['value'] != peak['value']:
        parts.append(f"O menor volume observado foi {dose_display(minimum['value'])}, em " +
                     ', '.join(month_label(p) for p in minimum['periods']) + '.')
    increases = summary.get('increases_before_last_peak', [])
    if increases:
        increase = max(increases, key=lambda t: Fraction(t['absolute_change']))
        parts.append(f"O maior aumento até esse máximo ocorreu de {month_label(increase['from_period'])} a {month_label(increase['period'])}: {dose_display(increase['previous_value'])} → {dose_display(increase['value'])} doses/registros.")
    declines = summary['declines_after_last_peak']
    if declines:
        parts.append('Após o último mês de maior volume, houve redução frente ao mês anterior em ' +
                     ', '.join(month_label(t['period']) for t in declines[:3]) +
                     (' e outros meses.' if len(declines) > 3 else '.'))
    if summary['total_is_partial']:
        parts.append('Há meses indisponíveis; o total soma somente os volumes observados.')
    return ' '.join(parts)


def _plot_dynamics(chart):
    if chart is None:
        return
    baseline = alt.Chart(pd.DataFrame({'zero': [0]})).mark_rule(color=NEUTRAL_REFERENCE).encode(y='zero:Q')
    base = chart.copy()
    base.config = alt.Undefined
    st.altair_chart((base + baseline).configure_axis(labelFontSize=12, titleFontSize=13).configure_view(stroke=None), width='stretch')


def render_monthly(payload, question=''):
    from .analytics.percentage import summarize_series
    result = deepcopy(payload['result'])
    result['data']['rows'] = calendar_rows(result)
    rows = result['data']['rows']
    temporal = result['operation'] == 'temporal'
    provenance = result.get('provenance', {})
    canonical = [{'period': row['period'], 'value':
                  Decimal(row.get('value' if temporal else 'doses'))
                  if isinstance(row.get('value' if temporal else 'doses'), str)
                  else row.get('value' if temporal else 'doses'),
                  'observation_status': row.get('observation_status')} for row in rows]
    summary = result['data'].get('summary') or summarize_series(canonical)
    st.subheader(question or 'Análise mensal')
    st.caption(f"{month_label(rows[0]['period'])} — {month_label(rows[-1]['period'])} · Doses/registros, não pessoas vacinadas")
    st.subheader('Resumo')
    cards = st.columns(3)
    provenance_metric(cards[0], 'Total observado' + (' (parcial)' if summary['total_is_partial'] else ''), dose_display(summary['observed_total']), 'DERIVED', 'total')
    provenance_metric(cards[1], 'Maior volume mensal', dose_display(summary['peak']['value']), 'DIRECT', 'peak')
    cards[1].caption(', '.join(month_label(p) for p in summary['peak']['periods']) or 'Indisponível')
    greatest = summary['greatest_absolute_changes']
    provenance_metric(cards[2], 'Maior mudança absoluta', dose_display(greatest[0]['absolute_change']) if greatest else '—', 'DERIVED', 'change')
    cards[2].caption('; '.join(f"{month_label(t['from_period'])} → {month_label(t['period'])}" for t in greatest) or 'Sem par consecutivo disponível')
    st.caption(f"{summary['observed_months']} meses observados · {summary['unavailable_months']} meses indisponíveis")

    provenance_heading('Volume mensal', 'DIRECT', 'volume_heading')
    chart = monthly_chart(result)
    if chart is not None:
        st.altair_chart(chart, width='stretch')
    else:
        st.info('Não há valores representáveis no gráfico; consulte a tabela exata.')
    missing = [month_label(r['period']) for r in canonical if r['value'] is None]
    if missing:
        st.info('Sem dados: ' + ', '.join(missing) + '. Ausência não significa zero.')

    if temporal:
        provenance_heading('Dinâmica mensal', 'DERIVED', 'dynamics_heading')
        order = provenance['order']
        percent_available = any('pct_change' in r.get('metrics', {}) for r in rows)
        selection = st.radio('Métrica derivada', ['Variação percentual', 'Diferença absoluta'], horizontal=True) if percent_available else 'Diferença absoluta'
        key = 'pct_change' if selection == 'Variação percentual' else f'delta_{order}'
        extremes = summary['extreme_increases']
        show_extreme = True
        if key == 'pct_change':
            st.caption('Variação do volume mensal em %. Não são pontos percentuais.')
            if extremes:
                st.warning('Variações acima de +100% podem resultar de uma base de comparação pequena. Elas são válidas e permanecem exatas no resultado e na tabela. Compare também os volumes em doses.')
                show_extreme = st.checkbox('Mostrar escala percentual completa, incluindo aumentos acima de +100%', value=False)
                if not show_extreme:
                    st.caption(f"Visão complementar: {len(extremes)} transições acima de +100% estão fora das barras e destacadas abaixo. Nenhum percentual foi truncado.")
                for transition in extremes:
                    st.write(f"**{month_label(transition['from_period'])} → {month_label(transition['period'])}**: " +
                             f"{dose_display(transition['previous_value'])} → {dose_display(transition['value'])} doses/registros " +
                             f"(diferença: {dose_display(transition['absolute_change'])}; +{percent_display(transition['pct_change'])}%).")
        else:
            st.caption(f"{LABELS[order]} · {provenance['formula']} · {provenance['units'][key]}")
        unavailable = [month_label(r['period']) for r in rows if r.get('metrics', {}).get(key, {}).get('value') is None]
        if unavailable:
            st.caption('Métrica indisponível: ' + ', '.join(unavailable))
        chart = monthly_chart(result, key, show_extreme=show_extreme)
        if chart is not None:
            _plot_dynamics(chart)
        else:
            st.info('Não há barras calculáveis nesta visão. Consulte os destaques e os detalhes científicos.')

    provenance_heading('Interpretação', 'DERIVED', 'interpretation_heading')
    st.write(contextual_summary(summary))
    filters = provenance.get('filters', payload.get('plan', {}))
    vaccine_text = filters.get('vaccine_text') or ''
    if ('influenza' in vaccine_text.casefold() and summary.get('increases_before_last_peak')
            and summary['declines_after_last_peak']):
        st.caption('O padrão pode ser compatível com uma dinâmica sazonal de vacinação, mas os dados de doses aplicadas, isoladamente, não permitem atribuir as mudanças à campanha nem confirmar sazonalidade.')
    st.caption('Descrição dos volumes observados; não demonstra causalidade, cobertura vacinal ou significância estatística.')

    with st.expander('Detalhes científicos · tabela exata, diferenças e proveniência'):
        table = monthly_table(result)
        classes = {column: ('DIRECT' if '(DIRECT)' in column else 'DERIVED')
                   for column in table.columns if '(DIRECT)' in column or '(DERIVED)' in column}
        st.caption('Colunas: DIRECT — Observado; DERIVED — Calculado. Valores exatos, sem alteração.')
        st.dataframe(style_provenance_table(table, classes), hide_index=True, width='stretch')
        if temporal:
            st.caption(f"Diferença solicitada: {provenance['formula']} · {provenance['units'][f'delta_{provenance['order']}']}")
            st.caption('Uma segunda diferença negativa pode representar crescimento ainda positivo, porém desacelerando.')
        st.caption('Nulls não são zero; diferenças não atravessam lacunas. Números sem representação segura no navegador permanecem na tabela exata.')
        for warning in result.get('warnings', []):
            st.warning(warning)
        st.download_button('Baixar tabela CSV', table.to_csv(index=False).encode('utf-8-sig'), 'sus_explorer_mensal.csv', 'text/csv', on_click='ignore')
        st.download_button('Baixar resultado e proveniência JSON', json.dumps(payload, ensure_ascii=False, indent=2), 'sus_explorer_resultado.json', 'application/json', on_click='ignore')
        st.json(payload.get('plan', {}))
        st.json(payload['result'])  # source result, not presentation placeholders


def render_result(payload, question=''):
    install_provenance_styles()
    render_provenance_legend()
    result = payload.get('result') or {}
    operation = result.get('operation')
    if operation in ('timeseries', 'temporal') and result.get('data', {}).get('rows'):
        render_monthly(payload, question)
        return
    data, provenance = result.get('data', {}), result.get('provenance', {})
    origin = provenance.get('source_provenance', provenance)
    if operation == 'count':
        provenance_metric(st, 'Doses/registros', str(data.get('doses', '—')), 'DIRECT', 'count')
    elif operation == 'group' and data.get('rows'):
        rows = data['rows']
        table = pd.DataFrame(rows)
        labels = [str(row.get('official_display') or row.get('value') or row.get('code') or row.get('display') or '—') for row in rows]
        frame = pd.DataFrame({'Grupo': labels, 'Doses/registros': [chart_number(row['count']) for row in rows],
                              'Origem': provenance_label('DIRECT')})
        provenance_heading('Doses/registros por grupo', 'DIRECT', 'group_heading')
        st.altair_chart(alt.Chart(frame).mark_bar(color=PROVENANCE_STYLES['DIRECT']['color']).encode(
            x='Doses/registros:Q', y=alt.Y('Grupo:N', sort='-x'), tooltip=['Grupo', 'Doses/registros', 'Origem']), width='stretch')
        enriched = {(i, column) for i, row in enumerate(rows) if documented_enrichment(row)
                    for column in ('definition', 'definition_source') if column in table.columns}
        if enriched:
            st.markdown(badge_html('ENRICHED'), unsafe_allow_html=True)
            st.caption('Somente as definições acompanhadas de fonte externa são contextualizadas. As contagens continuam DIRECT — Observado.')
        st.dataframe(style_provenance_table(table.astype(str), {'count': 'DIRECT'}, enriched), hide_index=True, width='stretch')
    elif operation == 'latency':
        provenance_heading('Latência operacional · dias', 'DERIVED', 'latency_heading')
        columns = st.columns(3)
        for column, key, label in zip(columns, ('median_days', 'p90_days', 'p95_days'),
                                      ('Mediana', 'P90', 'P95')):
            value = data.get(key)
            provenance_metric(column, label, str(value) if value is not None else '—', 'DERIVED', f'latency_{key}')
        st.caption(f"Registros válidos: {data.get('n_valid', '—')}")
    st.subheader('Interpretação')
    st.write(percentage_summary(data['rows']) if operation == 'temporal' and any('pct_change' in r.get('metrics', {}) for r in data.get('rows', [])) else payload.get('answer') or 'Nenhuma interpretação disponível.')
    for warning in result.get('warnings', []):
        st.warning(warning)
    st.download_button('Baixar resultado e proveniência JSON', json.dumps(payload, ensure_ascii=False, indent=2),
                       'sus_explorer_resultado.json', 'application/json', on_click='ignore')
    with st.expander('Plano, resultado e proveniência verificável'):
        st.caption(f"Operação: {operation} · Fragmentos: {origin.get('parquet_fragments', '—')} · Tempo de origem: {origin.get('elapsed_seconds', '—')} s")
        st.json(payload.get('plan', {}))
        st.json(result)
