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
real. A integração mantém somente Python e Streamlit; o protótipo web separado foi excluído da entrega.

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

## Intervalos de anos completos

Em consultas mensais/temporais, `de 2024 a 2025`, `entre 2024 e 2025` e
`2024 até 2025` representam janeiro de 2024 a dezembro de 2025, inclusive.
O planner recebe essa regra e o backend aplica a convenção a um único intervalo
explícito de anos, sem meses/dias/subperíodos na pergunta. Só o esclarecimento
atribuído à ausência de datas é liberado; UF ou outros requisitos ausentes
continuam obrigatórios. As operações descritivas count/group não são alteradas.

Meses explícitos prevalecem. `Janeiro a junho de 2024 em relação a 2025` pede
comparação interanual, ainda fora do contrato de diferenças consecutivas; não
é convertido em janeiro/2024 a dezembro/2025. O prompt deve informar essa
limitação, sem solicitar um intervalo contínuo que mude a pergunta.

Validação atualizada: **280 passed, 7 skipped, 0 failed**, incluindo 13 casos
de convenção anual, integração com o planner e preservação de subperíodos.

## Correção do filtro textual de vacina

O resultado enviado pelo usuário em 2026-10-08 continha seis observações zero,
207 fragmentos e o filtro `vaccine_text=influenza`. O filtro anterior procurava
somente o substring no texto de origem; uma coluna contendo INF3/INF4 não
correspondia a influenza. Essa falha foi reproduzida com Parquet sintético.
O arquivo agregado enviado não contém os valores brutos das colunas, portanto
não permite comprovar sozinho a grafia presente no R2.

O filtro agora corresponde ao texto original **ou** a `co_vacina` resolvido pela
terminologia MS + SES-GO já existente. Usa apenas rótulos canônicos e definições
sem conflito; não fixa códigos nem expande siglas por memória. A união não
conta uma linha duas vezes e continua combinada com os outros filtros.
A proveniência registra códigos efetivamente resolvidos, método e versões
públicas da terminologia, inclusive no resultado temporal. Sem terminologia
acessível, a consulta falha em vez de fabricar uma série zero. O cache existente
continua permitindo operação quando as fontes estiverem offline.

Não há alteração nas fórmulas, lacunas, ausência de observações anteriores,
classificações ou contagens sem filtro de vacina. Artefatos científicos,
migrations, armazenamento e auditoria permanecem preservados. A resolução
pode incluir várias apresentações da mesma família textual; os códigos ficam
explícitos na proveniência. Sinônimos ausentes da terminologia não são inferidos.

Verificação: `python -m pytest tests -q -rs` — **287 passed, 7 skipped, 0 failed**.
Inclui união sem duplicação, siglas/códigos, conflitos, filtros adicionais,
lacunas e diferenças exatas em série variável. Ainda é necessário repetir a
consulta real no ambiente com Gemini/R2 para verificar os totais corrigidos.
