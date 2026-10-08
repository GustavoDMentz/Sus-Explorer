from __future__ import annotations

import streamlit as st
from sus_explorer.service import SUSExplorer
from sus_explorer.streamlit_views import render_result

st.set_page_config(page_title='SUS Explorer', page_icon='💉', layout='wide')
st.title('SUS Explorer')
st.caption('Explore os dados públicos de vacinação com perguntas em linguagem natural.')
st.info('Cálculos no backend Python, com proveniência. Nenhum microdado individual é enviado ao LLM.')


@st.cache_resource
def get_explorer():
    return SUSExplorer()


with st.sidebar:
    st.header('Como consultar')
    st.write('Informe a UF e o período. Para análise temporal, use um intervalo mensal.')
    st.caption('Exemplos')
    st.write('Qual foi a variação mensal das doses no RS de janeiro a junho de 2026?')
    st.write('A vacinação contra influenza no RS está acelerando de janeiro a junho de 2026?')
    st.write('Quantas doses foram aplicadas em Porto Alegre, RS, em maio de 2026?')
    st.caption('Consultas remotas podem levar alguns minutos. Alterar a visualização não refaz a consulta.')

with st.form('query_form'):
    question = st.text_area('Sua pergunta', key='query_question', placeholder='Qual foi a variação mensal das doses no RS de janeiro a junho de 2026?')
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
    st.caption(st.session_state.get('result_question', ''))
    if payload.get('needs_clarification'):
        st.warning(payload.get('clarification_question') or 'Informe os parâmetros ausentes.')
        with st.expander('Plano parcial'):
            st.json(payload.get('plan', {}))
    else:
        render_result(payload)
