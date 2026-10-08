# Interface Streamlit

A interface principal usa o serviço SUSExplorer diretamente, sem API HTTP
intermediária e sem timeout de 90/200 segundos no navegador para `/api/ask`.
Isso não acelera a leitura remota: planejamento, agregação e explicação ainda
podem levar minutos e mantêm os timeouts dos respectivos clientes externos.

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Configure Gemini/R2 no `.env` como antes. PostgreSQL continua opcional. A branch
inclui as correções do planner previamente validadas pelo usuário em consulta
real. A interface Next.js permanece no repositório como protótipo opcional.

## Visualização

- Formulário explícito com botão Explorar, spinner com tempo decorrido e resultado
  guardado na sessão. Reruns e downloads não refazem a consulta ao Gemini/R2.
- Séries mensais DIRECT: gráfico de doses/registros e tabela de valores exatos.
- Temporal DERIVED: gráfico separado da diferença solicitada, fórmula, unidade,
  motivos estruturados de indisponibilidade e observações DIRECT preservadas.
- Lacunas e nulls interrompem os segmentos dos gráficos; nunca viram zero.
- Inteiros acima do limite seguro do JavaScript e decimais que perderiam precisão
  são omitidos do gráfico, mas preservados como texto na tabela e no JSON.
- Count: total; group: barras e tabela; latency: mediana/P90/P95 operacional.
- Exportações CSV mensal e JSON com resultado/proveniência; detalhes do plano,
  avisos e interpretação fornecida pelo backend.

A apresentação não recalcula diferenças, não infere cobertura ou causalidade e
não altera filtros, contratos de consulta, Parquet/R2, PostgreSQL, logging,
auditoria ou artefatos científicos. Dados reais só aparecem após uma consulta;
não há dados demonstrativos ou microdados na interface. A sessão guarda apenas
o último resultado agregado; não há cache global de resultados de consultas.

## Verificação

Testes com Streamlit AppTest e mocks cobrem submissão única, persistência após
rerun, clarificação, operações anteriores, lacunas e precisão da apresentação.
A suíte completa também valida o backend temporal e os contratos existentes.

Validação local em 2026-10-08: `python -m pytest tests -q -rs` — **267 passed,
7 skipped, 0 failed**. Os sete testes PostgreSQL exigem banco descartável e
não foram executados neste ambiente. Os 14 testes novos incluem a execução
real do app via AppTest com o serviço mockado; não há chamada Gemini/R2 real
nesses testes. A velocidade de consultas remotas não foi reavaliada.
