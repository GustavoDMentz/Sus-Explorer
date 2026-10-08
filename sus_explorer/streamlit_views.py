"""Presentation of aggregate results only; no query or analytics calculations."""
from decimal import Decimal, InvalidOperation
import math
import json

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


def monthly_table(result):
    temporal = result.get('operation') == 'temporal'
    records = []
    for row in result.get('data', {}).get('rows', []):
        record = {'Período': row['period'], 'Doses/registros (DIRECT)':
                  str(row.get('value' if temporal else 'doses')) if row.get('value' if temporal else 'doses') is not None else '—'}
        for key, metric in row.get('metrics', {}).items():
            record[f'{key} (DERIVED)'] = str(metric['value']) if metric['value'] is not None else '—'
            record[f'Razão ({key})'] = '; '.join(
                f"{reason['code']} ({reason['period']})" for reason in metric.get('unavailable_reasons', []))
        records.append(record)
    return pd.DataFrame(records)


def monthly_chart(result, key=None):
    """Separate line segments prevent connections across unavailable months."""
    rows = result.get('data', {}).get('rows', [])
    records, segment, previous = [], 0, None
    for row in rows:
        period = pd.Period(row['period'], freq='M')
        value = (row.get('metrics', {}).get(key, {}).get('value') if key
                 else row.get('value' if result['operation'] == 'temporal' else 'doses'))
        number = chart_number(value)
        if previous is not None and period.ordinal != previous.ordinal + 1:
            segment += 1
        if number is None:
            segment += 1
        else:
            records.append({'Período': period.to_timestamp(), 'Valor': number, 'Trecho': str(segment)})
        previous = period
    if not records:
        return None
    frame = pd.DataFrame(records)
    return alt.Chart(frame).mark_line(point=True).encode(
        x=alt.X('Período:T', title='Mês', axis=alt.Axis(format='%Y-%m')),
        y=alt.Y('Valor:Q', title='Doses/registros' if key is None else key,
                scale=alt.Scale(zero=False)), detail='Trecho:N',
        tooltip=[alt.Tooltip('Período:T', format='%Y-%m'), 'Valor:Q'],
    ).properties(height=280)


def render_result(payload):
    result = payload.get('result') or {}
    operation = result.get('operation')
    data, provenance = result.get('data', {}), result.get('provenance', {})
    origin = provenance.get('source_provenance', provenance)
    columns = st.columns(3)
    columns[0].metric('Operação', operation or '—')
    columns[1].metric('Fragmentos consultados', origin.get('parquet_fragments', '—'))
    elapsed = origin.get('elapsed_seconds')
    columns[2].metric('Tempo da consulta de origem', f'{elapsed:.1f} s' if isinstance(elapsed, (int, float)) else '—')

    if operation in ('timeseries', 'temporal') and data.get('rows'):
        st.subheader('Doses/registros por mês · DIRECT')
        chart = monthly_chart(result)
        if chart is not None:
            st.altair_chart(chart, width='stretch')
        if operation == 'temporal':
            order = provenance['order']
            key = f'delta_{order}'
            st.subheader(f'{LABELS[order]} · DERIVED')
            st.caption(f"{provenance['formula']} · {provenance['units'][key]}")
            chart = monthly_chart(result, key)
            if chart is not None:
                st.altair_chart(chart, width='stretch')
            else:
                st.info('Não há diferenças disponíveis para o intervalo consultado.')
            st.caption('Uma segunda diferença negativa pode representar crescimento ainda positivo, porém desacelerando. Diferenças finitas não demonstram causalidade ou inflexão confirmada.')
        st.caption('Meses ausentes e diferenças indisponíveis não são zero. Os gráficos não conectam lacunas. Valores que não podem ser representados com segurança no navegador ficam apenas na tabela exata.')
        table = monthly_table(result)
        st.subheader('Tabela mensal · valores exatos')
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
    st.write(payload.get('answer') or 'Nenhuma interpretação disponível.')
    for warning in result.get('warnings', []):
        st.warning(warning)
    st.download_button('Baixar resultado e proveniência JSON', json.dumps(payload, ensure_ascii=False, indent=2),
                       'sus_explorer_resultado.json', 'application/json', on_click='ignore')
    with st.expander('Plano, resultado e proveniência verificável'):
        st.json(payload.get('plan', {}))
        st.json(result)
