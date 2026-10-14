# SUS Explorer

**Exploração de microdados públicos do SI-PNI com linguagem natural, análise determinística e proveniência verificável.**

O SUS Explorer permite consultar dados de vacinação disponibilizados pelo Ministério da Saúde, armazenados em **Parquet no Cloudflare R2**, por meio de perguntas em português. O **Gemini interpreta a intenção e produz um plano estruturado**; o **Python valida os parâmetros, executa os cálculos e produz os resultados**. O modelo pode explicar os agregados, mas não é autoridade sobre contagens ou métricas.

**Nenhum microdado individual é enviado ao LLM.** Os resultados apresentados são agregados e devem ser interpretados como **doses/registros**, não como pessoas vacinadas ou cobertura vacinal.

> **Estado do projeto:** MVP em desenvolvimento, com interface principal em Streamlit. Disponibilidade de meses, filtros e resultados depende das partições Parquet efetivamente acessíveis e da configuração do ambiente.

## O que o projeto faz

- **Perguntas em linguagem natural:** planejamento com Gemini, `QueryPlan` tipado e validação Pydantic antes da execução.
- **Consultas determinísticas:** contagens, agrupamentos, séries mensais e indicadores de latência entre vacinação e entrada na RNDS.
- **Análise temporal:** diferenças finitas mensais de primeira, segunda e terceira ordem (Δ1, Δ2 e Δ3), variação mensal **MoM** e comparação com o mesmo mês do ano anterior **YoY**.
- **Visualização Streamlit:** volumes absolutos como referência principal, tabelas exatas, filtros e informações de proveniência; percentuais superiores a +100% recebem **barras visualmente interrompidas**, com valor real preservado e opção de escala completa.
- **Terminologia de imunobiológicos:** códigos e nomes canônicos do Ministério da Saúde, com definições complementares da SES-GO somente quando compatíveis.
- **Rastreabilidade:** proveniência dos dados e das transformações, logging estruturado e mecanismos de auditoria.
- **Exportação:** CSV para tabelas mensais e JSON dos resultados com proveniência, quando aplicável.

### Proveniência

| Classe | Significado | Identidade visual |
| --- | --- | --- |
| **DIRECT** | Observado nos dados consultados | Verde `#16A34A` |
| **DERIVED** | Calculado deterministicamente a partir das observações | Roxo `#9333EA` |
| **ENRICHED** | Contextualizado com informação externa documentada | Azul `#2563EB` |

A classificação é aplicada a cada informação, não indiscriminadamente a toda a consulta. A presença de uma legenda **não** significa que determinado resultado possua enriquecimento externo.

## Como funciona

```text
Pergunta em português
        │
        ▼
Gemini → plano JSON estruturado
        │
        ▼
Pydantic → validação do QueryPlan
        │
        ▼
Python / PyArrow → consulta Parquet no Cloudflare R2
        │
        ▼
Agregações, análise temporal e proveniência
        │
        ├──► Streamlit: gráficos, tabelas e exportações
        └──► Gemini: explicação baseada em agregados
```

O LLM **não executa SQL, não acessa o bucket diretamente e não calcula os valores apresentados**. Consultas analíticas usam o backend Parquet/R2; o PostgreSQL é uma camada operacional independente e opcional.

## Requisitos e instalação

- **Python 3.12 ou superior**, conforme as dependências atuais; o CI utiliza Python 3.12.
- Acesso e credenciais válidas para **Gemini** e **Cloudflare R2** nas consultas remotas.
- **PostgreSQL** somente para operações de persistência que o utilizem.

```bash
git clone https://github.com/GustavoDMentz/Sus-Explorer.git
cd Sus-Explorer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edite `.env` com as configurações necessárias, consultando `.env.example`. **Não versione credenciais nem publique seu arquivo `.env`.** PostgreSQL não é inicializado automaticamente durante imports ou consultas Parquet/R2.

### Interface principal — Streamlit

```bash
python -m streamlit run app.py
```

Digite uma pergunta e clique em **Explorar**. A consulta é executada mediante submissão explícita; o último resultado permanece na sessão, e mudanças de visualização normalmente não repetem a consulta remota. A opção YoY pode exigir **uma nova consulta explícita** para recuperar o mesmo período do ano anterior.

Não é necessário iniciar **Uvicorn, FastAPI ou Next.js** para a interface principal.

Mais detalhes: [Interface Streamlit](docs/streamlit.md).

### CLI

```bash
python demo.py "Quantas doses foram aplicadas em Porto Alegre, RS, em maio de 2026?"
```

### Teste de acesso a dados, sem LLM

```bash
python smoke_test.py
```

O teste de fumaça consulta a partição **RS / maio de 2026** no R2. Requer a configuração de acesso remoto; **não** é um teste totalmente offline.

### Testes automatizados

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q -rs
```

A suíte contém testes unitários e de interface com mocks. Testes de integração PostgreSQL requerem um banco descartável configurado; a execução local sem esse banco pode apresentar skips. A execução da suíte não equivale a validar contagens reais no Gemini/R2.

## Operações analíticas

| Operação | Resultado |
| --- | --- |
| `count` | Contagem de doses/registros |
| `group` | Agrupamentos por dimensões disponíveis, incluindo imunobiológico, município, sexo, idade, dose, CNES, sistema de origem e raça/cor |
| `timeseries` | Série mensal de doses/registros |
| `latency` | Mediana, P90 e P95 do intervalo entre vacinação e entrada na RNDS, para registros válidos |
| `temporal` | Diferenças mensais Δ1–Δ3, variação MoM e comparação interanual YoY |

**MoM** compara o volume com o mês imediatamente anterior. **YoY** compara com o mesmo mês do ano anterior, mantendo os filtros aplicados. YoY pode tornar séries sazonais mais legíveis, mas não elimina diferenças de calendários de campanha, população-alvo ou disponibilidade de dados.

Mês ausente **não vira zero**; diferenças não atravessam lacunas. Percentuais com denominador zero permanecem indisponíveis. Os gráficos podem arredondar valores para apresentação, mas tabelas e exportações preservam os resultados exatos.

Documentação: [Análise temporal](docs/temporal_analytics.md) · [Integração com QueryPlan](docs/temporal_queryplan.md).

## Armazenamento e arquitetura híbrida

O SUS Explorer mantém **dois backends complementares**:

- **Parquet / Cloudflare R2:** armazenamento e leitura analítica dos microdados e cubos, com acesso via PyArrow.
- **PostgreSQL:** persistência operacional opt-in para estado e proveniência de ingestões, documentos JSONB, revisões imutáveis e projeções normalizadas.

O PostgreSQL **não substitui** o Parquet/R2 e não é um fallback silencioso das consultas. A extensão **pgvector** está disponível como fundação para uma possível recuperação/RAG futura; sua presença **não** significa que embeddings ou RAG já façam parte das respostas.

Para iniciar o banco local:

```bash
docker compose up -d postgres
python -m sus_explorer.data.persistence.migrate
```

Para testes de integração, **use apenas um banco descartável**:

```bash
SUS_EXPLORER_TEST_DB=1 python -m pytest tests/integration
```

Documentação: [Arquitetura](docs/architecture.md) · [Persistência PostgreSQL](docs/persistence.md).

## Terminologia oficial MS + SES-GO

O catálogo de imunobiológicos utiliza:

- **Ministério da Saúde / BRImunobiologico:** autoridade para `code` e `official_display`.
- **SES-GO / BRImunobiologico:** fonte complementar para `definition`, incorporada apenas quando o nome do mesmo código é compatível com o nome canônico do MS.

Se houver divergência, `definition` permanece `null` e `terminology_conflict` é marcado como `true`. O LLM não deve completar a definição por memória.

O cache local fica em:

```text
~/.cache/sus_explorer/BRImunobiologico_ms_go.json
```

Para atualizar e verificar a terminologia:

```bash
python refresh_terminology.py
```

Exemplo de linha agregada (RS, maio de 2026; **não** corresponde a um registro individual):

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

## Limitações e interpretação

- `uf=` identifica a **UF do estabelecimento**, não necessariamente a residência da pessoa vacinada.
- O projeto conta **doses/registros**, não indivíduos únicos, efetividade, eficácia ou cobertura vacinal.
- **Cobertura vacinal não é calculada** no MVP; dependeria de denominadores e definições de população-alvo compatíveis.
- O comportamento temporal é **descritivo**: aumentos, quedas e diferenças não comprovam campanhas como causa, nem significância estatística.
- Séries interanuais não garantem equivalência entre estratégias oficiais distintas.
- Informações externas só devem receber `ENRICHED` quando acompanhadas de fonte verificável.
- A disponibilidade e completude das partições devem ser verificadas; dados ausentes não autorizam estimativas implícitas.

**Comparação entre campanhas oficiais:** há trabalho de desenvolvimento para combinar calendários do Ministério da Saúde e doses observadas. Não confundir essa funcionalidade em evolução com um consolidado oficial já reconciliado e disponível para todas as campanhas.

## Documentação técnica

- [Interface e visualizações](docs/streamlit.md)
- [Análise temporal](docs/temporal_analytics.md)
- [Contrato temporal e QueryPlan](docs/temporal_queryplan.md)
- [Arquitetura](docs/architecture.md)
- [Persistência PostgreSQL](docs/persistence.md)
- [Diário de desenvolvimento](docs/development_journal.md)

---

**Fontes de dados:** Ministério da Saúde / SI-PNI, com terminologia complementar documentada da SES-GO quando aplicável. O SUS Explorer é um projeto independente de exploração analítica de dados públicos; seus resultados não substituem indicadores oficiais do Ministério da Saúde.
