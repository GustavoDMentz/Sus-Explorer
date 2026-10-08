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

## Refinamento temporal e variação percentual

Diagnóstico: o gráfico anterior usava marcações automáticas num eixo temporal
contínuo e rótulos YYYY-MM. Os meses sem pontos podiam ser meses ausentes,
valores null, histórico insuficiente para a diferença ou números não
representáveis com segurança no navegador. TemporalAnalytics já completava o
intervalo com nulls explícitos e interrompia diferenças através de lacunas;
não havia motivo para imputar zero ou alterar doses. A consulta mensal agrega
por mês, ordena os períodos e o adaptador rejeita duplicidade/desordem.

O cabeçalho mostra pergunta e intervalo; cards mostram observações disponíveis,
meses indisponíveis e último volume. O eixo tem até oito marcações de meses reais
com rótulos portugueses jan/26, fev/26 etc. A linha DIRECT tem marcadores apenas
em valores disponíveis; segmentos separados interrompem lacunas. Séries
`timeseries` esparsas ganham placeholders null **somente na apresentação**, entre
primeiro e último mês retornado, sem modificar o contrato nem os dados salvos.

A operação `temporal` acrescenta `metrics.pct_change`, calculada deterministicamente
em `analytics/percentage.py` após a validação da série e antes da serialização.
Não muda as diferenças finitas nem a consulta de origem:

`pct_change(t) = 100 * (y(t) - y(t-1)) / y(t-1)`

- Somente pares de meses consecutivos; não lê meses anteriores ao intervalo.
- Histórico insuficiente, mês/valor ausente e denominador zero retornam null
  e `unavailable_reasons` estruturados. Zero observado é diferente de ausência.
- Int e Decimal finitos são aceitos; floats/bools rejeitados. Fraction preserva
  a razão exata, mesmo para dízimas e sob contexto Decimal de precisão reduzida.
- `value` é uma string racional exata: `25`, `-20` ou `100/3`. A diferença
  absoluta correspondente também é exata. JSON e tabela exata preservam isso.
  Somente gráficos/tooltips e texto resumido arredondam na apresentação.
- Proveniência adicional `percentage_change` registra fórmula, método v1.0.0,
  DERIVED, unidade %, políticas de ausência/zero e referência SHA-256 original.

O segundo gráfico alterna percentual e diferença absoluta **solicitada**, com
barras divergentes e referência zero. Tooltips exibem valor, unidade,
DIRECT/DERIVED, referência e diferença absoluta. Meses indisponíveis são listados
explicitamente e nunca aparecem como 0%. A tabela exata fica num expander.
O resumo percentual descreve os últimos dois pares calculáveis; ordens 2/3
mantêm também a interpretação da última diferença disponível. A projeção externa
para o LLM permanece com a diferença solicitada; o resumo percentual é local e
determinístico, usando os valores calculados. Sem nova dependência ou frontend.

Verificação: `python -m pytest tests -q -rs`. Casos cobrem crescimento, queda,
zero, denominador zero, lacunas/nulls, um mês, virada de ano, ordenação/duplicidade,
números grandes e Decimal exato, preservação das diferenças, séries esparsas,
limite de ticks e alternância Streamlit sem nova consulta. AppTest executa a
interface com mocks; não acessa Gemini/R2 real. Captura de navegador indisponível
neste ambiente (binário Chromium ausente). O comando amplo `pytest -q` também
coleta `smoke_test.py`, que exige configuração R2; a suíte do CI é `pytest tests`.

Resultado local final: **303 aprovados, 7 pulados, 0 falhos**, com 16 novos
casos. Os sete skips são integrações PostgreSQL sem banco descartável local;
nenhuma validação de totais reais Gemini/R2 foi realizada nesta etapa.

## Contexto de volumes, campanhas e percentuais extremos

A apresentação mensal segue: **Resumo → Volume mensal → Dinâmica mensal →
Interpretação → Detalhes científicos**. O volume DIRECT em doses continua
sendo o gráfico principal, com escala independente do percentual. O resumo
DERIVED mostra soma exata dos meses observados (parcial quando há nulls), máximo
mensal observado e maior diferença absoluta em magnitude, preservando o sinal.
Empates de máximo e de mudança são explicitados. Sem observações, total e máximo
são indisponíveis, nunca zero fabricado.

`analytics/percentage.py::summarize_series` gera esse resumo no resultado temporal
com versão e referência da série na proveniência. Usa a função exata de diferenças
já existente; somente pares consecutivos observados entram nas transições.
O resumo descritivo não modifica dados, diferenças ou percentuais. Na apresentação
de timeseries/retornos anteriores, a mesma função recebe exclusivamente os
agregados disponíveis, sem mudar o resultado original ou sua exportação.

Aumentos estritamente maiores que +100% permanecem exatos no resultado e tabela.
Na visão percentual padrão, essas barras são **omitidas explicitamente**, sem
truncar valores nem mudar os volumes. A tela lista cada transição, doses anterior
e atual, diferença absoluta e percentual, e explica o possível efeito de uma
base pequena. O checkbox **Mostrar escala percentual completa** inclui novamente
todas as barras; alternância e checkbox não repetem consultas. +100% continua no
gráfico complementar normal. Percentual com denominador zero continua null,
mesmo quando a diferença absoluta existe. Nenhuma escala é compartilhada entre
doses e percentuais. Valores fora da representação finita do navegador seguem
preservados nos detalhes exatos.

O texto contextual é determinístico: máximo e mínimo observados, maior aumento
até o último máximo e meses com redução consecutiva depois dele. Não descreve
queda através de lacunas nem assume redução monotônica. Quando o filtro textual
identifica influenza e há aumento até o máximo seguido de redução, a nota diz
que o padrão pode ser compatível com dinâmica sazonal, mas não confirma
sazonalidade nem atribui mudanças à campanha. Não deduz família vacinal de códigos
isolados nem consulta calendário externo. Não infere causalidade, pessoas
vacinadas, cobertura ou significância. Percentuais de volume não são pontos
percentuais.

Validação local: `python -m pytest tests -q -rs` — **314 aprovados, 7 pulados,
0 falhos**; 11 novos casos, incluindo crescimento abrupto/pico/queda, lacunas,
zero no denominador, empates, todos os meses ausentes, Decimal sob precisão
reduzida, +100% versus >+100%, preservação de resultados e hierarquia/checkbox
com Streamlit AppTest. Os sete skips exigem PostgreSQL descartável, ausente.
Não foram realizadas consultas Gemini/R2 reais. Sem novas dependências,
serviços, migrations ou alterações aos artefatos científicos.
