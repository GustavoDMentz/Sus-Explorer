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

st.set_page_config(page_title='SUS Explorer', page_icon='💉', layout='wide',
                   initial_sidebar_state='expanded')
st.title('SUS Explorer')
st.caption('Dados públicos de vacinação · consultas verificáveis em doses e registros')


def get_explorer():
    """Per-session explorer: never cache user credentials globally."""
    explorer = st.session_state.get('byok_explorer')
    if explorer is None:
        raise RuntimeError('Configure suas credenciais na barra lateral antes de consultar.')
    return explorer


def configure_byok():
    with st.sidebar.expander('Credenciais privadas (BYOK)', expanded=True):
        st.caption('Informe somente sua chave Gemini. O acesso ao healthbr-data é compartilhado e configurado pelo projeto.')
        with st.form('byok_credentials', clear_on_submit=False):
            gemini = st.text_input('Chave Gemini', type='password', key='byok_gemini')
            save = st.form_submit_button('Usar credenciais nesta sessão')
        if save:
            if not gemini.strip():
                st.error('Informe sua chave Gemini.')
            else:
                try:
                    st.session_state['byok_explorer'] = SUSExplorer(gemini_api_key=gemini.strip())
                    st.session_state.pop('query_result', None)
                    st.session_state.pop('query_error', None)
                    st.success('Credenciais configuradas para esta sessão.')
                except Exception:
                    st.session_state.pop('byok_explorer', None)
                    st.error('Não foi possível inicializar as credenciais. Confira os dados.')
        if st.button('Limpar credenciais e resultados', key='byok_clear'):
            for key in ('byok_explorer', 'byok_gemini', 'query_result',
                        'query_error', 'result_question', 'history_error', 'recent_queries', 'analytical_versions', 'session_query_history'):
                st.session_state.pop(key, None)
            st.rerun()




def remember_query(question, payload):
    """Keep a small, session-only list; never write questions to PostgreSQL."""
    if payload.get('needs_clarification') or not payload.get('result'):
        return
    entries = st.session_state.setdefault('session_query_history', [])
    entries.insert(0, {
        'question': question,
        'query_id': payload.get('query_id'),
        'operation': (payload.get('plan') or {}).get('operation', '—'),
        'result': deepcopy(payload),
    })
    del entries[20:]


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
    version_info = get_explorer()._observe_result(plan, result)
    updated['version_history'] = version_info if isinstance(version_info, dict) else {'status': 'disabled'}
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


configure_byok()

with st.sidebar:
    st.header('Como consultar')
    st.write('Informe a UF e o período. Para análise temporal, use um intervalo mensal.')
    st.caption('Exemplos')
    st.write('Qual foi a variação mensal das doses no RS de janeiro a junho de 2026?')
    st.write('A vacinação contra influenza no RS está acelerando de janeiro a junho de 2026?')
    st.write('Quantas doses foram aplicadas em Porto Alegre, RS, em maio de 2026?')
    st.caption('Consultas remotas podem levar alguns minutos. Alterar a visualização não refaz a consulta.')
    with st.expander('Recursos desta sessão'):
        st.checkbox('Reconhecer datas e consultas simples automaticamente (REGEX)', value=True, key='regex_planner_enabled', help='Reconhece apenas padrões completos e seguros. Perguntas mais complexas continuam usando Gemini.')
        st.checkbox('Guardar histórico nesta sessão', value=True, key='session_history_enabled', help='Até 20 consultas, somente na memória desta sessão do Streamlit. Não requer PostgreSQL.')
        st.caption('Histórico persistente e executor híbrido exigem configuração administrativa e não são ativados por este controle.')

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
            st.session_state.pop('analytical_versions', None)
            try:
                with st.spinner('Planejando, consultando os dados e preparando o resultado. Aguarde…', show_time=True):
                    explorer = get_explorer()
                    explorer.llm.deterministic_enabled = st.session_state.get('regex_planner_enabled', True)
                    st.session_state.query_result = explorer.ask(question.strip())
                st.session_state.result_question = question.strip()
                if st.session_state.get('session_history_enabled', True):
                    remember_query(question.strip(), st.session_state.query_result)
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
            vh = payload.get('version_history') or {}
            if vh.get('status') == 'saved':
                st.caption('Histórico analítico: versão ' + str(vh['version']) +
                           (' · resultado alterado' if vh.get('changed') else ' · sem alteração'))
                if st.button('Ver versões desta consulta', key='load_analytical_versions'):
                    try:
                        from sus_explorer.data.persistence.result_versions import get_versions
                        st.session_state['analytical_versions'] = get_versions(vh['query_key'])
                    except Exception:
                        st.error('Não foi possível verificar as versões históricas.')
                if versions := st.session_state.get('analytical_versions'):
                    if versions and versions[-1]['version'] == vh['version']:
                        st.dataframe(pd.DataFrame([{
                            'Versão': v['version'], 'Primeira observação': v['first_seen_at'],
                            'Última observação': v['last_seen_at'],
                            'Verificações': v['observations'],
                        } for v in versions]), hide_index=True, width='stretch')
            elif vh.get('status') == 'unavailable':
                st.warning('Consulta concluída, mas o histórico analítico não pôde ser salvo.')
            render_result(payload, st.session_state.get('result_question', ''), execute_yoy_comparison)

with history_tab:
    st.subheader('Histórico desta sessão')
    st.caption('Consultas mantidas somente na memória da sessão atual; não exige PostgreSQL.')
    if st.button('Limpar histórico da sessão', key='clear_session_history'):
        st.session_state.pop('session_query_history', None)
        st.rerun()
    entries = st.session_state.get('session_query_history', [])
    if not entries:
        st.info('Nenhuma consulta registrada nesta sessão.')
    else:
        for i, entry in enumerate(entries):
            with st.expander(f"{entry['operation']} · {entry['question'][:100]}", expanded=False):
                st.caption('Identificador: ' + str(entry.get('query_id') or '—'))
                if st.button('Abrir resultado', key=f'open_session_query_{i}'):
                    st.session_state['query_result'] = deepcopy(entry['result'])
                    st.session_state['result_question'] = entry['question']
                    st.session_state.pop('query_error', None)
                    st.info('Resultado restaurado. Abra a aba Explorador de dados para visualizá-lo.')

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
