# SUS Explorer

## Apresentação

Explorador experimental de registros públicos de vacinação do SI-PNI. Uma pergunta em português chega ao Gemini, que propõe um `QueryPlan`; Pydantic valida o plano; Python consulta Parquet no Cloudflare R2 e calcula os agregados; Streamlit apresenta números, explicação e proveniência. O modelo não calcula os números nem recebe microdados individuais.

> **Estado:** MVP em desenvolvimento. Disponibilidade e correção das respostas dependem das partições remotas, da configuração e da interpretação do Gemini. Este README descreve o código atual; resultados históricos em `docs/` não substituem uma validação do ambiente de destino.

## Sumário

- [Apresentação](#apresentação)
- [Objetivos e escopo](#objetivos-e-escopo)
- [Funcionalidades implementadas](#funcionalidades-implementadas)
- [Funcionalidades experimentais e limitações](#funcionalidades-experimentais-e-limitações)
- [Arquitetura do sistema](#arquitetura-do-sistema)
- [Fluxo de uma consulta](#fluxo-de-uma-consulta)
- [Tecnologias utilizadas](#tecnologias-utilizadas)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Pré-requisitos](#pré-requisitos)
- [Instalação no Windows](#instalação-no-windows)
- [Instalação no Linux/macOS](#instalação-no-linuxmacos)
- [Configuração do Gemini](#configuração-do-gemini)
- [Configuração do Cloudflare R2](#configuração-do-cloudflare-r2)
- [Configuração do PostgreSQL](#configuração-do-postgresql)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Docker Compose](#docker-compose)
- [Migrations](#migrations)
- [Ingestão controlada](#ingestão-controlada)
- [Persistência e histórico](#persistência-e-histórico)
- [Roteamento híbrido](#roteamento-híbrido)
- [Execução do Streamlit](#execução-do-streamlit)
- [Testes automatizados](#testes-automatizados)
- [Testes com serviços reais](#testes-com-serviços-reais)
- [Troubleshooting](#troubleshooting)
- [Segurança e gerenciamento de credenciais](#segurança-e-gerenciamento-de-credenciais)
- [Limitações conhecidas](#limitações-conhecidas)
- [Próximos passos tecnicamente justificados](#próximos-passos-tecnicamente-justificados)
- [Guia de contribuição](#guia-de-contribuição)

## Fonte dos dados, créditos e agradecimentos

O SUS Explorer utiliza os arquivos Parquet disponibilizados pelo projeto **[healthbr-data](https://github.com/SidneyBissoli/healthbr-data)**, desenvolvido e mantido por **Sidney da Silva Bissoli**. A fonte primária dos registros é o **Ministério da Saúde / OpenDATASUS**; o healthbr-data realiza a redistribuição em formato analítico, com particionamento e acesso via Cloudflare R2.

**Nosso agradecimento especial ao Sidney Bissoli** pelo trabalho de engenharia de dados, manutenção e disponibilização aberta dessa infraestrutura. A organização dos dados em Parquet e a publicação de acesso S3 de leitura pública tornam viáveis análises que, de outra forma, exigiriam esforços substanciais de transferência, transformação e operação. O SUS Explorer é um projeto independente e não deve ser confundido com o healthbr-data; reconhecemos expressamente essa contribuição fundamental.

O repositório de origem declara licença **CC BY 4.0**. Consulte [a licença e as orientações de citação do projeto](https://github.com/SidneyBissoli/healthbr-data#license) e atribua também a fonte primária Ministério da Saúde / OpenDATASUS quando utilizar os dados em trabalhos ou publicações. O SUS Explorer não reivindica autoria dos dados ou do espelho Parquet.

## Estado das integrações recentes (20/10/2026)

- **Implementado na `master`:** Streamlit com instância `SUSExplorer` por sessão; formulário BYOK **somente para Gemini**, com R2 compartilhado configurado pelo projeto; planejador determinístico experimental via `SUS_DETERMINISTIC_PLANNER=1`; histórico operacional PostgreSQL opt-in (migration 004); histórico de resultados agregados versionados e criptografados opt-in (migration 005, `ANALYTICAL_HISTORY_ENABLED=1`, `ANALYTICAL_HISTORY_KEY`).
- **Não integrado:** [#17](https://github.com/GustavoDMentz/Sus-Explorer/pull/17) (campanhas), [#26](https://github.com/GustavoDMentz/Sus-Explorer/pull/26) (PyArrow 26), [#33](https://github.com/GustavoDMentz/Sus-Explorer/pull/33) (limite de pergunta) e [#34](https://github.com/GustavoDMentz/Sus-Explorer/pull/34) (histórico visual por sessão). Os PRs #33/#34 são drafts, com testes adicionados mas não validados nesta revisão.
- **Segurança e limites:** o histórico operacional atual na UI não tem filtro de usuário; a criptografia do histórico analítico não é controle de autorização por usuário. O runtime PostgreSQL e a segregação de microdados exigem testes de privilégio em banco descartável. O compromisso é assumir comprometimento e limitar danos, não alegar isolamento absoluto entre sessões do mesmo processo.
- **Rastreabilidade:** [registro dos PRs](docs/pr_register.md), [diário de desenvolvimento](docs/development_journal.md), [contrato do histórico versionado](docs/query-result-version-history.md), [persistência](docs/persistence.md), [Streamlit](docs/streamlit.md). Evidências e números de testes datados não significam que a suíte foi refeita nesta revisão documental.

## Objetivos e escopo

O projeto explora **doses/registros**, não pessoas únicas. Cada linha consultada representa um registro de vacinação; não há deduplicação confiável por indivíduo nem denominador populacional adequado para calcular cobertura vacinal. A UF usada nas partições é a **UF do estabelecimento**, não necessariamente a residência do paciente. A análise é descritiva e não prova causalidade, efetividade ou significância epidemiológica.

## Funcionalidades implementadas

- Planejamento estruturado por Gemini, validação Pydantic e esclarecimento quando faltam UF ou período; pedidos diários são recusados.
- Contagem, agrupamento, séries mensais e estatísticas de latência RNDS sobre Parquet/R2. Filtros disponíveis dependem das colunas da origem.
- Diferenças finitas mensais de ordens 1 a 3, variação absoluta e percentual MoM e comparação com o mesmo mês do ano anterior (YoY). O intervalo mensal tem limite de 36 meses.
- Resultado exato e proveniência: `DIRECT` para observações, `DERIVED` para cálculos e `ENRICHED` somente quando há fonte complementar documentada. Mês sem partição é ausente; partição existente com zero registros é zero.
- Streamlit com tabela, gráficos, exportações quando aplicáveis, estado de sessão, origem da consulta e histórico opcional. Alterar uma visualização não repete a consulta; buscar uma referência YoY ausente requer ação explícita.
- Catálogo de imunobiológicos: código/nome do Ministério da Saúde, definição SES-GO somente quando compatível; conflito não é preenchido por adivinhação.
- PostgreSQL operacional opcional: migrations, ingestão explícita de uma partição R2, revisões/observações, projeções normalizadas, histórico de metadados e roteamento restrito de contagens elegíveis.

## Funcionalidades experimentais e limitações

O construtor de cubo, o manifest e a auditoria independente MS × cubo são ferramentas separadas da consulta ativa. O cubo derivado em `cache/pni_cube` ou em `sus-dados/cache/pni_cube` **não** é lido pelo `sus_explorer/pni.py` durante perguntas. A auditoria versionada de outubro de 2023 é um resultado histórico específico, não certificação de todas as partições. A extensão pgvector está presente como fundação; embeddings, RAG, chatbot com documentos e importação automática não estão ativos.

Gemini e R2 reais não são validados pela suíte padrão. A explicação do Gemini pode falhar ou divergir semanticamente; os números exibidos vêm do executor Python. Consultas a serviços reais exigem credenciais, custos e uma verificação independente dos dados esperados.

## Arquitetura do sistema

O Streamlit chama o serviço Python diretamente. O planejador, o executor analítico e o histórico PostgreSQL têm responsabilidades separadas. A ingestão e a auditoria são comandos administrativos fora da interface pública.

## Fluxo de uma consulta

```text
app.py (Streamlit)
  → sus_explorer/service.py (SUSExplorer)
  → llm.py (Gemini → QueryPlan)
  → schemas.py (Pydantic)
  → hybrid.py (roteamento determinístico)
      → pni.py (PyArrow → Parquet no R2, padrão)
      → PostgreSQL (somente count mensal/UF sem filtros e com cobertura comprovada)
  → analytics/ (diferenças, percentuais e YoY em Python)
  → llm.py (explicação dos agregados)
  → Streamlit; query_history.py → PostgreSQL opcional
```

O Gemini não recebe acesso ao bucket nem escreve SQL. Na análise temporal, `pni.py` agrega a série, `analytics/temporal_query.py` valida a origem e `analytics/temporal.py`, `percentage.py` e `yoy.py` calculam valores exatos. Diferenças não atravessam lacunas; percentual com denominador zero fica indisponível. YoY busca explicitamente o mesmo mês do ano anterior com os mesmos filtros. A referência SHA-256 da série identifica consulta e agregados; não prova por si só a identidade dos bytes do R2.

| Local | Conteúdo | Uso na consulta |
| --- | --- | --- |
| `healthbr-data/sipni/microdados` no R2 | Parquet de origem | Leitura analítica padrão por PyArrow |
| `sus-dados/cache/pni_cube` e cache local | Cubo derivado e manifest | Construção/auditoria; a consulta ativa não usa cache-first |
| PostgreSQL | Apenas partições selecionadas, revisões, observações e projeções | Contagem mensal elegível por opt-in; não substitui o R2 |
| PostgreSQL `query_history` | UUID, data, operação, parâmetros tipados, executor, estado, duração e proveniência limitada | Histórico; **não** guarda pergunta livre ou resultado completo e **não** é cache de resultados |

## Tecnologias utilizadas

Python, Streamlit, Pydantic, Google GenAI SDK, PyArrow, Pandas, PostgreSQL 17/pgvector, psycopg, Cloudflare R2 compatível com S3, pytest e GitHub Actions. `requirements.txt` define compatibilidade; `constraints.txt` fixa versões diretas revisadas para CI.

## Estrutura do repositório

| Caminho | Responsabilidade |
| --- | --- |
| `app.py`, `demo.py` | Interface principal e CLI de consulta |
| `sus_explorer/llm.py`, `schemas.py`, `service.py` | Plano, validação e orquestração |
| `sus_explorer/pni.py`, `hybrid.py`, `analytics/` | Leitura e cálculo analítico |
| `sus_explorer/data/persistence/` | Migrations, ingestão explícita, repositórios e histórico |
| `sus_explorer/build_cache.py`, `data/cache/`, `cli/audit_ms.py` | Cubo, manifest e auditoria independente |
| `tests/unit`, `tests/integration`, `tests/e2e` | Níveis A, B e C de teste |
| `docs/` | Registro histórico e especificações detalhadas; este README rege a operação atual |

## Pré-requisitos

Use Python 3.12 ou superior compatível com as dependências; o CI usa 3.12. Acesso à internet e chave Gemini são necessários nas consultas remotas. O acesso ao bucket público de leitura do healthbr-data pode ser pré-configurado pelo projeto; instalações personalizadas podem sobrescrever R2_* no ambiente. PostgreSQL é opcional para a aplicação; Docker Desktop ou Docker Engine é necessário para o script de teste com banco descartável.

## Instalação no Windows

```powershell
git clone https://github.com/GustavoDMentz/sus-explorer.git
Set-Location sus-explorer
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints.txt -r requirements-dev.txt
Copy-Item .env.example .env
```

Instale Python 3.12 antes, se necessário. Edite `.env` antes de consultar serviços. Usar o executável da `.venv` evita o alias `python` da Microsoft Store.

## Instalação no Linux/macOS

```bash
git clone https://github.com/GustavoDMentz/sus-explorer.git
cd sus-explorer
python3.12 -m venv .venv
.venv/bin/python -m pip install -c constraints.txt -r requirements-dev.txt
cp .env.example .env
```

Os comandos Python são portáveis; o script `scripts/test_postgres.ps1` é específico de PowerShell. No Linux/macOS, configure manualmente um banco **descartável** para os testes PostgreSQL.

## Configuração do Gemini

Obtenha uma chave válida para o projeto e configure `GEMINI_API_KEY`; `GEMINI_MODEL` seleciona o modelo de planejamento e explicação. Nenhuma chave de exemplo é fornecida. Uma chave ausente impede criar o serviço.

## Configuração do Cloudflare R2

Configure `R2_ENDPOINT`, `R2_ACCESS_KEY`, `R2_SECRET_KEY`, bucket e prefixo da origem Parquet com permissão de leitura. O bucket independente de auditoria usa `SUS_DATA_R2_*`; não existe fallback automático de um para o outro.

## Configuração do PostgreSQL

O banco é opcional. Quando habilitado, configure host, porta, banco, usuário, senha e schema; mantenha `POSTGRES_COUNT_ENABLED=0` e `POSTGRES_HISTORY_ENABLED=0` até aplicar migrations e conferir permissões. Use credenciais distintas para migração, runtime e leitura fora do desenvolvimento local.

## Variáveis de ambiente

`sus_explorer/config.py` lê `.env` via `python-dotenv` na importação; a conexão PostgreSQL lê variáveis quando aberta. Altere `.env` antes de iniciar o Streamlit, pois o serviço é mantido em cache. Copie `.env.example`; deixe opcionais desativados até configurá-los. Exemplo sem segredos:

```dotenv
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.5-flash-lite
R2_ENDPOINT=
R2_ACCESS_KEY=
R2_SECRET_KEY=
R2_REGION=auto
R2_BUCKET=healthbr-data
R2_PREFIX=sipni/microdados
POSTGRES_COUNT_ENABLED=0
POSTGRES_HISTORY_ENABLED=0
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=sus_explorer
POSTGRES_USER=sus_explorer
POSTGRES_PASSWORD=
POSTGRES_SCHEMA=sus_explorer
POSTGRES_SSLMODE=prefer
```

| Grupo | Uso |
| --- | --- |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Planejamento e explicação. A chave vazia impede criar `GeminiAnalyst`. |
| `R2_ENDPOINT`, `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_REGION`, `R2_BUCKET`, `R2_PREFIX` | Leitura PyArrow dos Parquet da consulta ativa. Endpoint deve ser o do serviço S3 da conta. |
| `SUS_DATA_R2_*` | Bucket e credenciais **independentes** de auditoria do cubo; não são fallback da consulta. |
| `POSTGRES_COUNT_ENABLED`, `POSTGRES_HISTORY_ENABLED` | Flags independentes, valores `0`/`1`; ambas desativadas por padrão. |
| `POSTGRES_HOST`, `PORT`, `DB`, `USER`, `PASSWORD`, `SCHEMA`, `SSLMODE` | Conexão operacional. Para banco remoto use TLS verificado (`verify-full`) e CA confiável. |
| `POSTGRES_CONNECT_TIMEOUT`, `POSTGRES_STATEMENT_TIMEOUT_MS`, `POSTGRES_LOCK_TIMEOUT_MS`, `POSTGRES_IDLE_TRANSACTION_TIMEOUT_MS`, `POSTGRES_APPLICATION_NAME` | Limites e identificação da conexão; defaults em `.env.example`. |

As credenciais de auditoria são `SUS_DATA_R2_ENDPOINT`, `SUS_DATA_R2_ACCESS_KEY_ID`, `SUS_DATA_R2_SECRET_ACCESS_KEY`, `SUS_DATA_R2_BUCKET` e `SUS_DATA_R2_CUBE_PREFIX`. `MAX_GROUP_ROWS` limita resultados de agrupamento; padrão 50.

## Docker Compose

O Compose publica PostgreSQL somente em `127.0.0.1`. Defina uma senha local em `.env` antes de `docker compose`; o arquivo não contém senha versionada. **Volumes existentes mantêm credenciais e dados da inicialização anterior**; mudar `.env` não altera usuários já criados. Não use o banco persistente para a suíte destrutiva.

```powershell
docker compose config --quiet
docker compose up -d postgres
.\.venv\Scripts\python.exe -m sus_explorer.data.persistence.healthcheck
.\.venv\Scripts\python.exe -m sus_explorer.data.persistence.migrate
```

No Linux/macOS, substitua `.\.venv\Scripts\python.exe` por `.venv/bin/python`.

## Migrations

O comando `sus_explorer.data.persistence.migrate` acima aplica, na ordem, as versões 001–004: fundação e pgvector; hardening e roles; índices de partição; histórico de consultas. O migrador usa transação, lock e SHA-256; não possui down migration nem detecta mudanças manuais fora das versões. Para bancos existentes, confira previamente usuário, extensão pgvector e janela de manutenção para criação de índices. Não reescreva arquivos SQL já aplicados: o checksum fará a execução falhar.

## Ingestão controlada

A ingestão é comando administrativo explícito de **uma** partição mensal/UF; Streamlit não a inicia. Requer R2 real, banco preparado e identidade `co_documento` no Parquet.

```powershell
.\.venv\Scripts\python.exe -m sus_explorer.data.persistence.ingest_r2 --year 2026 --month 5 --uf RS --batch-size 1000
```

Antes de escrever, valida colunas/tipos e captura SHA-256 dos fragmentos. Cada lote é transacional. Reexecução com mesmo payload registra observação sem duplicar raw; mudança arquiva a revisão anterior. Linhas inválidas/duplicadas impedem status `SUCCESS`; interrupção pode ser retomada somente no mesmo snapshot e em execução `RUNNING`:

```powershell
.\.venv\Scripts\python.exe -m sus_explorer.data.persistence.ingest_r2 --year 2026 --month 5 --uf RS --resume-run-id 123
```

`PARTIAL` e `FAILED` não comprovam cobertura. Não rode este comando como teste de instalação em dados reais.

## Persistência e histórico

`POSTGRES_HISTORY_ENABLED=1` grava metadados da tentativa, inclusive falha após obter o plano. Falha de histórico não altera o resultado analítico; a interface indica indisponibilidade.

## Roteamento híbrido

`POSTGRES_COUNT_ENABLED=1` só permite PostgreSQL para `count` sem filtros, em uma partição `year`/`month`/`uf`, se a execução mais recente está completa e hash, fragmentos, linhas, observações e projeções ainda correspondem ao R2. Caso contrário, consulta R2. Séries, agrupamentos, latência, temporal e contagens filtradas permanecem no R2.

O hash dos arquivos é recalculado na consulta elegível, o que pode ser caro. Roles de migração, runtime e leitura são distintas; não use a credencial de migração no serviço. Payloads individuais no banco exigem política própria de acesso/retenção antes de produção.

## Execução do Streamlit

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Digite uma pergunta com UF e período e clique **Explorar**. Exemplo: “Qual foi a variação mensal das doses no RS de janeiro a abril de 2026?”. A resposta numérica está na tabela/JSON exato; gráficos podem arredondar a apresentação. A aba de fontes indica o executor analítico; histórico só aparece quando habilitado. Sem PostgreSQL, deixe as duas flags em `0`. Falta de Gemini ou R2 impede executar uma nova pergunta e aparece como erro genérico na UI.

```powershell
.\.venv\Scripts\python.exe demo.py "Quantas doses foram aplicadas no RS em maio de 2026?"
.\.venv\Scripts\python.exe smoke_test.py
```

`smoke_test.py` consulta R2 real sem LLM; não é teste offline. `refresh_terminology.py`, `recover_pni_2023_10.py` e a auditoria são ferramentas administrativas separadas; consulte `--help` ou o código antes de executá-las em fontes reais.

## Testes automatizados

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rs
.\.venv\Scripts\python.exe -m pytest tests -m unit -q
.\.venv\Scripts\python.exe -m pytest tests -m integration -q -rs
```

`pytest.ini` limita a coleta a `tests/` e marca `unit` (A), `integration` (B) e `external` (C). A classificação indica componentes exercitados, não que todo teste B use banco: `tests/integration/test_local_query_pipeline.py` percorre PyArrow/Parquet local, análise e AppTest com o transporte Gemini substituído. Os testes PostgreSQL criam/removem schemas e só executam com `SUS_EXPLORER_TEST_DB=1` em banco descartável. No Windows, com Docker Desktop ativo:

```powershell
.\scripts\test_postgres.ps1
```

Esse script cria um contêiner temporário, senha aleatória, aplica migrations e executa a suíte, removendo somente o contêiner criado por ele. O workflow `test-postgres.yml` usa serviço PostgreSQL descartável no CI. `verify-r2.yml` é manual e verifica acesso/listagem de cache, não o fluxo Gemini → resposta. O diagnóstico por grupo e as lacunas estão em [Auditoria de testes](docs/test_audit.md).

Nesta revisão, o script concluiu health check, migrations 001–004 e **402 testes aprovados, 0 pulados, 1 externo deselecionado**. O contêiner temporário foi removido. A cobertura de branches combinada no mesmo tipo de banco foi 71% no pacote completo e 85% nos módulos críticos selecionados; detalhes no relatório.

## Testes com serviços reais

O teste C usa **Gemini e R2 reais**, Streamlit e histórico em schema descartável. Ele é excluído da suíte padrão, pode gerar custo de API e exige contagens de referência independentes para dois meses consecutivos. Só execute em ambiente controlado com `SUS_EXPLORER_EXTERNAL_TEST=1`, `SUS_EXPLORER_TEST_DB=1`, `POSTGRES_DB` terminado em `_test`, credenciais normais de Gemini/R2/PostgreSQL e `SUS_EXPLORER_EXTERNAL_YEAR`, `SUS_EXPLORER_EXTERNAL_MONTH` (2 a 12), `SUS_EXPLORER_EXTERNAL_UF`, `SUS_EXPLORER_EXTERNAL_COUNT` (mês selecionado) e `SUS_EXPLORER_EXTERNAL_PREVIOUS_COUNT` (mês anterior). Exemplo de invocação após configurar esses valores por um operador:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/e2e -m external -q -rs
```

Não coloque esses segredos em CI automático, argumentos de comando, commits ou logs. O teste não ingere dados e lê duas partições para uma contagem e uma variação mensal; seu resultado não certifica todas as perguntas ou partições. Um `skip` significa **não validado**, nunca aprovação do serviço real.

## Troubleshooting

| Sintoma | Verificação |
| --- | --- |
| `python` abre Microsoft Store | Use o Python da `.venv` ou `py -3.12` no Windows. |
| `GEMINI_API_KEY não configurada` | Preencha `.env`, reinicie o Streamlit e confira o projeto/chave fora do Git. |
| `Configuração R2 ausente` / erro de rede | Confira endpoint S3, bucket, prefixo, permissões de leitura e partição; não confunda os dois buckets. |
| Partição ausente | Não converta em zero; confirme publicação, ano, mês e UF do estabelecimento. |
| Histórico indisponível | Confira flag, conexão, schema, migration 004 e role runtime. O resultado analítico pode continuar válido. |
| Compose exige senha | Preencha `POSTGRES_PASSWORD` em `.env`; não use valor versionado. |
| PostgreSQL tests pulados | Execute `scripts/test_postgres.ps1` com Docker Desktop, ou prepare um banco descartável equivalente. |
| Plano temporal falha | Confira intervalo de até 36 meses, UF e formato da pergunta; saída inválida do Gemini pode provocar erro controlado. |

## Segurança e gerenciamento de credenciais

`.env` e variantes são ignorados pelo Git; `.env.example` contém apenas placeholders. Use credenciais R2 somente leitura para consulta e credenciais independentes para auditoria. Não passe credenciais PostgreSQL ao LLM. O histórico omite pergunta livre, texto de vacina/município e resultado completo. Logs operacionais removem segredos conhecidos, mas ainda exigem política de acesso. Antes de publicar, revise permissões de buckets, TLS do banco, roles separadas e retenção de payloads individuais.

## Limitações conhecidas

A suíte local confirmou PostgreSQL em contêiner descartável, mas não confirma Gemini/R2 reais; o workflow R2 manual verifica o cubo de auditoria, não as perguntas no backend ativo. O modelo pode interpretar uma intenção de forma incorreta mesmo quando o plano recebido é válido. O PostgreSQL materializa somente partições explicitamente selecionadas. A interface usa AppTest nos testes, sem captura de navegador real.

## Próximos passos tecnicamente justificados

- Reproduzir a falha de variação mensal no RS contra uma partição real conhecida e uma expectativa independente; o teste local cobre o caminho de cálculo sem provar o comportamento do Gemini ou R2 remoto.
- Executar o canário externo controlado e registrar plano, contagem esperada e proveniência sem expor dados ou credenciais. Validar erros de autenticação e rede em ambiente de staging.
- Medir cobertura de branches e mutações em cálculo, validação e roteamento; a aprovação de pytest não garante correção semântica do modelo nem dos dados de origem.
- Verificar esquema/identidade `co_documento`, custo de hash e recuperação de ingestão antes de ativar `POSTGRES_COUNT_ENABLED` em produção.
- Auditar mais partições do cubo contra fonte independente. Não generalizar a auditoria histórica de outubro de 2023.
- Resolver separadamente a duplicação de aliases e clientes S3 quando houver evidência de falha; a auditoria deve continuar independente do construtor.

## Guia de contribuição

Abra uma issue com pergunta, plano esperado, período/UF e evidência sanitizada. Para mudanças de cálculo, adicione um caso com valores esperados calculados independentemente, inclusive zero/ausência/erro. Rode a suíte A/B e, quando afetar persistência, o banco descartável; relate skips e testes externos separadamente. Não adicione segredos, dados individuais ou totais de produção sem fonte auditável. Preserve migrations aplicadas e documente novas versões. Não execute ingestões ou chamadas pagas como efeito colateral de testes padrão.

`docs/development_journal.md` preserva a cronologia; `docs/temporal_analytics.md`, `docs/temporal_queryplan.md`, `docs/architecture.md`, `docs/persistence.md` e `docs/streamlit.md` registram decisões e contratos detalhados de entregas anteriores. Em caso de divergência operacional, confira o código atual e atualize este README.
