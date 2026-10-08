# Integração TemporalAnalytics v1 ao QueryPlan

## Inspeção e decisão arquitetural

Base desta integração: `master` em `23589f2`, que já contém o PR #8.
O plano real é Pydantic (`schemas.py`), o planner/explainer usa Gemini
(`llm.py`), o executor é `PNIRemote` (`pni.py`) e a fachada é `SUSExplorer`
(`service.py`). `QueryResult` possui `operation/data/provenance/warnings` e
`model_dump()`. O cálculo puro é `analytics/temporal.py`.

O contrato de `timeseries` é `data.rows=[{"period":"YYYY-MM","doses":int}]`.
Conta registros mensais, usando UF do estabelecimento, município por código
IBGE ou nome, vacina por código ou substring textual, sexo e limites de idade.
Meses sem partição são omitidos e registrados em `missing_partitions`; ausência
de todas as partições produz `FileNotFoundError`. Os filtros de idade e vacina
textual podem exigir leitura de colunas internamente, mas só contagens saem do
backend para esta integração.

`DERIVED` existia no módulo temporal. `DIRECT`/`ENRICHED` não eram campos gerais
das consultas descritivas. A integração declara o vocabulário tipado
`ResultClassification` e classifica explicitamente as observações agregadas
de origem como `DIRECT` e as diferenças como `DERIVED`. Não reclassifica nem
altera os resultados antigos, e não introduz enriquecimento `ENRICHED`.

## Plano tipado

```json
{
  "status": "ready",
  "operation": "temporal",
  "uf": "RS",
  "vaccine_text": "influenza",
  "start_year": 2026,
  "start_month": 1,
  "end_year": 2026,
  "end_month": 6,
  "temporal_analysis": {
    "order": 2,
    "metric": "doses",
    "granularity": "monthly"
  }
}
```

`TemporalRequest` rejeita ordens fora de 1–3, bool/string/float como ordem,
métrica/granularidade não suportadas e campos extras. Planos temporais rejeitam
campos livres, intervalos inválidos ou invertidos, UF inválida, filtros inválidos,
`year/month/day/group_by` e `top_n` diferente do default legado. Código de
município deve ser IBGE público de 6/7 dígitos, código de vacina numérico explícito;
usar nome ou código de município, sem combinação silenciosamente ignorada.
Idade: 0–200, mínimo não maior que máximo. Anos suportados: 2020–2100.

UF, limites mensais e pedido temporal são essenciais. Se faltarem em um plano
temporal marcado `ready`, a validação converte para `needs_clarification`, sem
preencher o valor ausente. O executor também revalida planos antes da execução.
Os planos antigos continuam aceitos; o novo campo opcional é `null` quando não
usado. `temporal_analysis` em outra operação é rejeitado, evitando ignorá-lo.

O prompt distingue variação mensal (ordem 1), aceleração/desaceleração ou
crescimento perdendo força (ordem 2), e terceira diferença/mudança da aceleração
(ordem 3). Observar a trajetória da aceleração usa ordem 2; pedir sua diferença
usa ordem 3. Um pedido explícito de ano inteiro pode ser representado por janeiro
a dezembro daquele ano. "Está acelerando?" não autoriza escolher período recente.
Município não autoriza deduzir UF, e vacina textual não autoriza inventar código.

Exemplos sem intervalo, como "A vacinação contra influenza no RS está
acelerando?", precisam de esclarecimento. "Qual foi a variação mensal das doses
em Porto Alegre?" precisa também de UF. Não há memória de contexto multi-turn
adicionada nesta etapa: a próxima pergunta deve fornecer os parâmetros necessários.

## Execução e resultado

O adaptador `execute_temporal()` cria um plano `timeseries` com os mesmos filtros
e intervalo, chama o executor existente uma vez e valida sua operação/estrutura.
Seleciona apenas `period` e `doses`, rejeitando coerções numéricas silenciosas.
O módulo puro valida ordem, duplicatas, limites e tipos, calcula as três ordens
sem lógica duplicada; o adaptador apresenta somente a ordem solicitada.

Não são consultados meses anteriores ao início declarado. Lacunas e `None`
permanecem `null`, com razões estruturadas, e bloqueiam as janelas. Inteiros
continuam exatos; `Decimal` é serializado como string exata. A convenção é
regressiva, alinhada ao último mês, passo de um mês; unidade `doses/month^k`.
Ela não usa dias corridos, população, suavização ou normalização.

Proveniência: `DERIVED`, ordem, fórmula(s), método `1.0.0`, granularidade,
intervalo, parâmetros, filtros, unidade, política de ausências, consulta de
origem e proveniência pública dessa consulta. `source_series_ref` é SHA-256 de
JSON canônico da consulta mensal e das observações agregadas, com representação
decimal exata. Identifica os valores/consulta, não é hash dos arquivos Parquet
nem prova de auditoria científica da fonte. Tempos de execução não entram no hash.

As linhas mantêm `value`/`observation_status` e acrescentam
`observation_classification: DIRECT`. Cada métrica é `DERIVED`, com `value`,
`unavailable_reasons` e tag determinística `interpretation` do sinal local:

| Ordem | Positiva | Negativa |
|---|---|---|
| 1 | Volume mensal aumentando | Volume mensal diminuindo |
| 2 | Variação mensal aumentando | Variação mensal diminuindo |
| 3 | Segunda diferença aumentando | Segunda diferença diminuindo |

Zero indica ausência de mudança naquela diferença; `null` indica indisponibilidade.
Por exemplo, doses `[10,15,18,20]` têm segunda diferença `[null,null,-2,-1]`:
o volume cresce, mas a variação mensal diminui. Sinais locais não confirmam
causalidade, anomalias, mudança epidemiológica significativa ou inflexões.

## Proveniência segura e fronteira do LLM

Antes da apresentação, a proveniência de origem é projetada para campos públicos
do contrato atual: fonte canônica, UF, contagens de partições/fragmentos, tempo,
partições ausentes e indicador de ausência de microdados no LLM. Campos arbitrários,
URLs, IDs privados e objetos aninhados não são encaminhados. Rótulos de fonte
desconhecidos ficam `UNVERIFIED_SOURCE_LABEL`. O objeto original não é mutado.
Essa projeção sanitizada é explicitada por `metadata_policy`; não é uma alegação
de preservação de todos os metadados privados em uma saída pública.

A redação canônica de logging é reutilizada, incluindo secrets configurados e
variáveis de ambiente. Metadados contraditórios de UF/ausência e declaração de
envio de microdados são rejeitados. Linhas extras/microdados e warnings arbitrários
da origem são descartados. Warnings de ausência são gerados a partir da saída.

O explainer temporal recebe somente a projeção do resultado agregado, sem texto
livre da pergunta nem metadados arbitrários. Recebe também instruções para não
recalcular, corrigir ou substituir números. O texto probabilístico é separado do
resultado determinístico e nunca sobrescreve seus valores. Não há chamada ao
LLM no adaptador nem no cálculo, e não há SQL livre. O reconhecimento linguístico
real continua dependente do modelo; mocks testam o contrato do prompt/schema e
a integração, não garantem acerto de qualquer formulação em produção.

## Falhas controladas

`TemporalQueryError` informa código e mensagem genérica, sem exceção bruta da
origem: `SOURCE_QUERY_FAILED` para consulta indisponível/falha;
`INVALID_SOURCE_SERIES` para estrutura/tipos/metadados incompatíveis;
`INVALID_TEMPORAL_PLAN` para plano incompleto. Sem origem válida, não há resposta
do explainer. Nenhum fallback PostgreSQL ou transformação de ausência em zero.

## Validação local desta entrega

```text
python -m pytest tests -q
234 passed, 7 skipped in 1.10s

python -m pytest tests/integration -q
7 skipped in 0.05s
```

Nenhum teste falhou. Os sete testes PostgreSQL existentes exigem banco
descartável, indisponível neste ambiente. O workflow existente do PR fornece
PostgreSQL 17 + pgvector para executar a suíte integral; seus resultados serão
registrados no PR após consulta dos logs. `compileall` e `git diff --check`
aprovados. Os 90 novos casos usam mocks Gemini, séries sintéticas e datasets
PyArrow em memória, sem API Gemini nem bucket real.

Arquivos desta integração: `schemas.py`, `llm.py`, `pni.py`, `service.py`,
`analytics/temporal_query.py`, `tests/unit/test_temporal_query.py`,
`docs/temporal_queryplan.md`, `docs/temporal_analytics.md`, `docs/architecture.md`.
Sem novas dependências, alterações em migrations, artefatos científicos,
publicação atômica de auditoria ou logging. Frontend, API HTTP, atividade pública,
suavização, anomalias, cobertura e testes estatísticos permanecem fora do escopo.
