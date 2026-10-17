from __future__ import annotations

import os
import time
from uuid import uuid4
import pandas as pd
import streamlit as st
from sus_explorer.service import SUSExplorer
from sus_explorer.schemas import QueryPlan
from copy import deepcopy
from sus_explorer.streamlit_views import render_result
from sus_explorer.data.persistence.history import recent_queries

st.set_page_config(page_title='SUS Explorer', page_icon='💉', layout='wide',
                   initial_sidebar_state='expanded')
st.title('SUS Explorer')
st.caption('Dados públicos de vacinação · consultas verificáveis em doses e registros')


@st.cache_resource
def get_explorer():
    return SUSExplorer()


def execute_yoy_comparison(payload):
    updated = deepcopy(payload)
    plan_data = deepcopy(payload['plan'])
    temporal = plan_data.get('temporal_analysis') or {'order':1}
    plan_data.update(operation='temporal', temporal_analysis=temporal | {'comparison':'yoy'})
    plan = QueryPlan.model_validate(plan_data)
    query_id = uuid4()
    started = time.perf_counter()
    try:
        result = get_explorer().pni.execute(plan)
    except Exception:
        if os.getenv('POSTGRES_HISTORY_ENABLED') == '1':
            get_explorer()._record_history(
                query_id, plan, None, 'FAILED', int((time.perf_counter() - started) * 1000)
            )
        raise
    updated['result'] = result.model_dump()
    updated['plan'] = plan.model_dump()
    updated['answer'] = None  # do not reuse an explanation of a different comparison
    updated['query_id'] = str(query_id)
    updated['history_status'] = (
        get_explorer()._record_history(
            query_id, plan, result, 'SUCCESS', int((time.perf_counter() - started) * 1000)
        ) if os.getenv('POSTGRES_HISTORY_ENABLED') == '1' else 'disabled'
    )
    return updated


with st.sidebar:
    st.header('Como consultar')
    st.write('Informe a UF e o período. Para análise temporal, use um intervalo mensal.')
    st.caption('Exemplos')
    st.write('Qual foi a variação mensal das doses no RS de janeiro a junho de 2026?')
    st.write('A vacinação contra influenza no RS está acelerando de janeiro a junho de 2026?')
    st.write('Quantas doses foram aplicadas em Porto Alegre, RS, em maio de 2026?')
    st.caption('Consultas remotas podem levar alguns minutos. Alterar a visualização não refaz a consulta.')

explorer_tab, history_tab, sources_tab = st.tabs(
    ['Explorador de dados', 'Histórico', 'Fontes e proveniência']
)

with explorer_tab:
    st.info('Cálculos no backend Python, com proveniência. Nenhum microdado individual é enviado ao LLM.')
    with st.form('query_form'):
        question = st.text_area('Sua pergunta', key='query_question',
                                placeholder='Qual foi a variação mensal das doses no RS de janeiro a junho de 2026?')
        submitted = st.form_submit_button('Explorar', type='primary')

    if submitted:
        if not question.strip():
            st.warning('Digite uma pergunta para consultar.')
        else:
            st.session_state.pop('query_result', None)
            st.session_state.pop('query_error', None)
            try:
                with st.spinner('Planejando, consultando os dados e preparando o resultado. Aguarde…', show_time=True):
                    st.session_state.query_result = get_explorer().ask(question.strip())
                st.session_state.result_question = question.strip()
            except Exception:
                st.session_state.query_error = 'Não foi possível concluir a consulta. Confira a configuração e tente novamente.'

    if st.session_state.get('query_error'):
        st.error(st.session_state.query_error)

    if payload := st.session_state.get('query_result'):
        if payload.get('needs_clarification'):
            st.warning(payload.get('clarification_question') or 'Informe os parâmetros ausentes.')
            with st.expander('Plano parcial'):
                st.json(payload.get('plan', {}))
        else:
            if payload.get('history_status') == 'unavailable':
                st.warning('A consulta foi concluída, mas o histórico PostgreSQL não pôde ser gravado.')
            render_result(payload, st.session_state.get('result_question', ''), execute_yoy_comparison)

with history_tab:
    st.subheader('Consultas registradas')
    st.caption('Metadados de consultas; os resultados e as perguntas não são armazenados aqui.')
    if os.getenv('POSTGRES_HISTORY_ENABLED') != '1':
        st.info('Histórico PostgreSQL desativado neste ambiente.')
    elif st.button('Carregar histórico', key='load_history'):
        try:
            with st.spinner('Consultando histórico…'):
                st.session_state['recent_queries'] = recent_queries()
            st.session_state.pop('history_error', None)
        except Exception:
            st.session_state.pop('recent_queries', None)
            st.session_state['history_error'] = 'Histórico indisponível. Confira a conexão e as migrations PostgreSQL.'
    if os.getenv('POSTGRES_HISTORY_ENABLED') == '1':
        if st.session_state.get('history_error'):
            st.error(st.session_state['history_error'])
        elif 'recent_queries' in st.session_state:
            rows = st.session_state['recent_queries']
            if rows:
                frame = pd.DataFrame([{
                    'Data e hora': row['executed_at'], 'Consulta': str(row['id']),
                    'Operação': row['operation'], 'Executor': row['executor'].upper(),
                    'Status': row['status'], 'Duração (ms)': row['duration_ms'],
                    'Período': row['provenance'].get('period', '—'),
                } for row in rows])
                st.dataframe(frame, hide_index=True, width='stretch')
            else:
                st.info('Ainda não há consultas registradas.')

with sources_tab:
    st.subheader('Origem da consulta atual')
    payload = st.session_state.get('query_result')
    result = payload.get('result') if payload else None
    if not result:
        st.info('Execute uma consulta para ver a origem, o período e as partições analisadas.')
    else:
        provenance = result.get('provenance') or {}
        origin = provenance.get('source_provenance', provenance)
        executor = origin.get('executor', 'r2')
        columns = st.columns(3)
        columns[0].write('**Executor analítico**')
        columns[0].write('PostgreSQL' if executor == 'postgres' else 'R2 / Parquet')
        columns[1].write('**Período**')
        columns[1].write(str(origin.get('period') or '—'))
        columns[2].write('**Fragmentos Parquet**')
        columns[2].write(str(origin.get('parquet_fragments', '—')))
        st.caption('Doses/registros representam eventos de vacinação, não indivíduos únicos ou cobertura vacinal.')
        if origin.get('partitions'):
            st.write('Partições analisadas: ' + ', '.join(origin['partitions']))
        if origin.get('missing_partitions'):
            st.warning('Partições ausentes: ' + ', '.join(origin['missing_partitions']))
        if origin.get('source_sha256'):
            st.caption('SHA-256 da origem materializada: ' + origin['source_sha256'])
        if origin.get('ingestion_run_id'):
            st.caption('Execução de ingestão: ' + str(origin['ingestion_run_id']))
        if payload.get('history_status') == 'saved':
            st.caption('Histórico operacional salvo no PostgreSQL; o executor analítico aparece acima.')
