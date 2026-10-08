"""Independent campaign section; no remote queries or guessed campaign totals."""
import json

import altair as alt
import pandas as pd
import streamlit as st

from .analytics.campaigns import compare_campaigns, load_catalog
from .schemas import QueryPlan
from .streamlit_provenance import (PROVENANCE_STYLES,
    provenance_heading, style_provenance_table)
from .streamlit_views import chart_number


def campaign_chart(result):
    """Draw only comparable observations; exact large integers stay in details."""
    if result['data']['status'] != 'ready':
        return None
    daily = result['provenance']['mode'] == 'daily'
    comparable = {row['elapsed_day'] if daily else row['calendar_month']
                  for row in result['data']['comparison'] if row['difference'] is not None}
    records = []
    for row in result['data']['rows']:
        position = row['elapsed_day'] if daily else int(row['period'][5:7])
        number = chart_number(row['cumulative_doses'] if daily else row['observed_doses'])
        if position not in comparable or number is None:
            continue
        records.append({'Campanha': row['campaign'], 'Posição': position,
            'Período': row['period'], 'Valor': number,
            'Exato': str(row['cumulative_doses'] if daily else row['observed_doses']),
            'Origem': 'DERIVED — Calculado' if daily else 'DIRECT — Observado',
            'Fonte da série': result['provenance']['source_refs'][row['campaign_id']],
            'Calendário': 'ENRICHED — Contextualizado'})
    if not records:
        return None
    chart = alt.Chart(pd.DataFrame(records))
    if daily:
        chart = chart.mark_line(point=True, color=PROVENANCE_STYLES['DERIVED']['color']).encode(
            x=alt.X('Posição:Q', title='Dia decorrido desde o início previsto (dia 1 = início)'),
            strokeDash='Campanha:N', detail='Campanha:N')
    else:
        chart = chart.mark_bar(color=PROVENANCE_STYLES['DIRECT']['color']).encode(
            x=alt.X('Campanha:N', title=None), column=alt.Column('Posição:O', title='Mês calendário completo — aproximação'))
    return chart.encode(y=alt.Y('Valor:Q', title='Doses acumuladas' if daily else 'Doses no mês', scale=alt.Scale(zero=True)),
        tooltip=['Campanha:N', 'Período:N', 'Exato:N', 'Origem:N', 'Calendário:N', 'Fonte da série:N']).properties(height=320)


def render_campaigns(payload):
    catalog = load_catalog()
    st.divider()
    st.subheader('Comparação entre campanhas oficiais')
    st.caption('Seção independente · MVP influenza / Rio Grande do Sul · gráficos mensais e YoY preservados.')
    provenance_heading('Calendário oficial documentado', 'ENRICHED', 'campaign_calendar')
    st.caption(f'Catálogo {catalog.catalog_version} · verificado em {catalog.verified_on} · {catalog.scope}')
    for container, campaign in zip(st.columns(2), catalog.campaigns):
        with container:
            st.markdown(f'**{campaign.title}**')
            st.write(f'{campaign.start:%d/%m/%Y} — {campaign.end:%d/%m/%Y} · calendário previsto')
            st.caption(campaign.geographic_scope)
            st.markdown(f'[Fonte oficial MS: {campaign.source.title}]({campaign.source.url})')
            st.markdown(f'[Metadados oficiais da publicação]({campaign.source.metadata_url})')
            st.caption(f'Publicação: {campaign.source.publication_date or "não informada explicitamente"} · versão: {campaign.source.edition or "não informada"}')
    selection = st.radio('Janela de campanha', ['Primeiros 30 dias', 'Primeiros 60 dias',
        'Aproximação mensal — meses completos comuns'], key='sus_campaign_window', horizontal=True)
    daily = selection != 'Aproximação mensal — meses completos comuns'
    if not payload.get('plan'):
        st.info('A comparação exige um plano com filtros explícitos; o catálogo não fornece volumes de doses.')
        return
    try:
        plan = QueryPlan.model_validate(payload['plan'])
        result = compare_campaigns(plan, [c.id for c in catalog.campaigns],
            mode='daily' if daily else 'monthly', window_days=60 if selection == 'Primeiros 60 dias' else 30).model_dump()
    except ValueError:
        st.info('Os filtros deste resultado não permitem avaliar a comparação de campanhas. Nenhuma consulta adicional foi executada.')
        return
    st.caption('DIRECT: doses de uma extração verificada · DERIVED: acumulados e diferenças · ENRICHED: calendário oficial. Calendário não comprova doses.')
    # Fail closed until the existing pipeline exposes an audited campaign extract.
    # Do not consume a caller-provided dictionary as if it were verified evidence.
    chart = campaign_chart(result)
    if chart is not None:
        st.altair_chart(chart, width='stretch')
    else:
        st.info('Gráfico indisponível: faltam dados adequados e verificados para comparar estas campanhas. Nenhum volume foi estimado.')
    for reason in result['data']['unavailable_reasons']:
        st.caption(f"{reason['code']}: {reason['message']}" +
                   (f" ({reason['campaign_id']})" if reason.get('campaign_id') else ''))
    if not daily:
        st.caption('Maio é o único mês completo comum aos dois calendários; isso identifica uma janela candidata, não valida a fonte de doses nem autoriza o gráfico.')
    for warning in result['warnings']:
        st.caption(warning)
    with st.expander('Evidências e limitações da comparação de campanhas'):
        table = pd.DataFrame([{'Campanha': c.title, 'Início previsto (ENRICHED)': c.start.isoformat(),
            'Fim previsto (ENRICHED)': c.end.isoformat(), 'Fonte': c.source.url,
            'Localizador': c.source.calendar_locator, 'Registro': c.source.recording_locator,
            'Publicação': c.source.publication_date.isoformat() if c.source.publication_date else 'Não informada',
            'Nota de publicação': c.source.publication_date_note} for c in catalog.campaigns])
        st.dataframe(style_provenance_table(table, {'Início previsto (ENRICHED)': 'ENRICHED',
            'Fim previsto (ENRICHED)': 'ENRICHED'}), hide_index=True, width='stretch')
        st.caption('O contrato atual não certifica completude diária, pertencimento à campanha nem equivalência entre microdados e módulos de registro. Ausência não é zero. Esta seção não executa consultas remotas.')
        st.json(result)
        st.download_button('Baixar catálogo oficial e limitações', json.dumps(result, ensure_ascii=False, indent=2),
            'sus_explorer_campanhas.json', 'application/json', key='sus_campaign_download', on_click='ignore')
