# SUS Explorer — MVP

Protótipo para consultar microdados públicos do SI-PNI diretamente de Parquet remoto (Cloudflare R2), usando um LLM apenas para planejar consultas e explicar resultados agregados. **Microdados individuais não são enviados ao LLM.**

## Fluxo

Pergunta → Gemini (plano JSON) → Pydantic → PyArrow/R2 → agregado + proveniência → Gemini → resposta.

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edite `.env` e configure somente os backends que pretende usar. A consulta
analítica atual requer Gemini e R2; PostgreSQL é opcional e não é inicializado
durante imports ou consultas Parquet/R2.

## Teste sem LLM

```bash
python smoke_test.py
```

Deve contar a partição RS / maio de 2026 diretamente no R2.

## Interface principal — Streamlit

```bash
python -m streamlit run app.py
```

O Streamlit consulta diretamente o serviço Python: não é necessário iniciar
Uvicorn nem Next.js. A interface mostra gráficos mensais e diferenças temporais,
agrupamentos, tabelas exatas, exportações CSV/JSON e proveniência. Consultas só
são executadas ao clicar em **Explorar**; o resultado permanece na sessão.

Veja [`docs/streamlit.md`](docs/streamlit.md).

## CLI

```bash
python demo.py "Quantas doses foram aplicadas em Porto Alegre em maio de 2026?"
```

## Operações do MVP

- `count`: contagem de doses/registros;
- `group`: agrupamento por vacina, município, sexo, idade, dose, CNES, sistema de origem ou raça/cor;
- `timeseries`: série mensal;
- `latency`: mediana/P90/P95 entre vacinação e entrada na RNDS;
- `temporal`: diferenças mensais de ordem 1, 2 ou 3, calculadas no Python.

## Limites

- A partição `uf=` é a UF do estabelecimento.
- Tudo no SI-PNI remoto é tratado como dado público, mas nenhum registro individual é enviado ao Gemini.
- O LLM não escreve SQL e não acessa o bucket diretamente: ele só produz um `QueryPlan` validado.
- O MVP não calcula cobertura vacinal; isso entra depois com denominadores IBGE.

## Arquitetura híbrida

O projeto mantém dois backends complementares e suportados:

- **Parquet/R2:** camada analítica para microdados públicos e cubos, usada pelas
  operações `count`, `group`, `timeseries` e `latency`;
- **PostgreSQL:** persistência operacional opt-in para estado e proveniência de
  ingestões, documentos JSONB, revisões imutáveis e projeções normalizadas.

PostgreSQL não substitui nem é fallback silencioso para Parquet/R2. A extensão
pgvector é instalada como fundação para uma futura camada de recuperação/RAG,
mas esta mudança não cria embeddings nem altera respostas do assistente. O LLM
continua limitado ao planejamento validado e à explicação de agregados: ele não
é autoridade sobre números e não recebe microdados individuais.

Para iniciar um PostgreSQL local com pgvector:

```bash
docker compose up -d postgres
python -m sus_explorer.data.persistence.migrate
```

Use apenas banco descartável nos testes de integração:

```bash
SUS_EXPLORER_TEST_DB=1 python -m pytest tests/integration
```

O contrato operacional e as garantias do banco estão detalhados em
[`docs/persistence.md`](docs/persistence.md).


## Merge de terminologia MS + SES-GO

A versão atual usa:

- **Ministério da Saúde / BRImunobiologico** como autoridade para `code` e
  `official_display`.
- **SES-GO / BRImunobiologico** para `definition`.

A definição da SES-GO só é incorporada se o `display` do mesmo código for
compatível com o display canônico do MS. Em divergência:

```json
{
  "definition": null,
  "terminology_conflict": true
}
```

O LLM é instruído a nunca completar a descrição por memória própria.

O cache fica em:

```text
~/.cache/sus_explorer/BRImunobiologico_ms_go.json
```

Para atualizar e testar o merge:

```bash
python refresh_terminology.py
```

Uma linha de agrupamento por vacina passa a ter a forma:

```json
{
  "code": "33",
  "display": "INF3",
  "official_display": "INF3",
  "definition": "Vacina influenza trivalente",
  "definition_source": "SES-GO / BRImunobiologico",
  "terminology_conflict": false,
  "count": 616927
}
```
