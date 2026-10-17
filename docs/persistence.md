# Persistência operacional PostgreSQL

## Papel no sistema

PostgreSQL complementa o backend analítico Parquet/R2. Ele registra operações
de ingestão, proveniência da fonte, representações JSONB, histórico de revisões
e projeções normalizadas. R2 permanece o executor padrão. Apenas a contagem
sem filtros de uma única partição mensal/UF pode usar PostgreSQL, por opt-in e
após conferência de cobertura e versão exata dos arquivos R2.

O histórico de consultas é um recurso separado, habilitado com
`POSTGRES_HISTORY_ENABLED=1`. A migration `004_query_history.sql` cria uma tabela
de metadados: UUID, instante, operação, parâmetros estruturados, executor
analítico, status, duração e proveniência limitada. Não grava perguntas,
prompts, microdados ou resultados completos. `result_ref` fica nulo enquanto
não houver armazenamento externo de resultados. Uma falha na gravação é mostrada
na interface como histórico indisponível; o resultado analítico continua válido.
O histórico **não** é cache de resultados.

## Inicialização e verificação no Windows (PowerShell)

Use um PostgreSQL descartável para testes. Com Docker Desktop ativo, o script
abaixo cria um contêiner com armazenamento temporário, senha aleatória local,
porta vinculada a `127.0.0.1`, executa `SELECT 1`, migrations e a suíte inteira,
e remove o contêiner ao final. Ele não usa as credenciais de `.env` nem altera
o banco configurado para desenvolvimento/produção.

```powershell
.\scripts\test_postgres.ps1
```

O teste de integração cria schemas com nomes aleatórios, aplica migrations,
grava ingestões e histórico, relê dados após nova conexão e remove apenas seus
schemas. `SUS_EXPLORER_TEST_DB=1` deve ser usado **somente** com banco descartável;
o script o configura apenas no seu processo. Para desenvolvimento persistente,
preencha `.env` a partir de `.env.example`, execute `docker compose up -d postgres`,
depois o health check e a migration. Em um banco existente, confira host, nome,
usuário e permissão antes de aplicar migrations; a migration não apaga/recria o banco.

Validação local em 17/10/2026 com Docker Desktop e
`pgvector/pgvector:0.8.6-pg17`: `SELECT 1`, migrations `001`–`004` e
`.\scripts\test_postgres.ps1` concluídos; **397 testes aprovados, 0 pulados,
0 falhas**. O contêiner descartável foi removido após a execução. Essa prova
usa Parquet sintético local nos testes de ingestão; não comprova acesso a R2 ou
Gemini reais nem migração em banco de produção.

Para verificar dados gravados, conecte um leitor ao schema configurado e use:

```sql
SELECT id, status, records_received, source_resource_id
FROM sus_explorer.datasus_ingestion_runs ORDER BY id DESC LIMIT 20;
SELECT id, operation, executor, status, duration_ms
FROM sus_explorer.query_history ORDER BY executed_at DESC LIMIT 20;
```

Se `SELECT 1` falhar, confira a disponibilidade do serviço e as variáveis
`POSTGRES_*`; o comando não imprime senha nem DSN. Se a migration falhar, confira
extensão `vector`, roles e permissões de migração. Se a ingestão ficar `PARTIAL`,
inspecione contagens e esquema da partição selecionada; não habilite a contagem
PostgreSQL como se a cobertura fosse completa. Se o histórico ficar indisponível,
confira se `004_query_history.sql` foi aplicada e se o login de runtime recebeu
`sus_explorer_runtime`.

## Ingestão controlada R2 → PostgreSQL

Após aplicar as migrations existentes e configurar R2 e PostgreSQL, selecione
explicitamente **uma** partição mensal/UF:

```bash
python -m sus_explorer.data.persistence.ingest_r2 --year 2026 --month 5 --uf RS --batch-size 1000
```

O comando não inicia ingestões automaticamente nem varre o histórico. Exige
`co_documento` textual como identidade estável e única, além de `co_vacina`,
`dt_vacina`, `co_municipio_estabelecimento` e `sg_uf_estabelecimento`. Ausência
ou tipo incompatível de coluna impede a criação da execução. Datas e UFs
inválidas tornam a execução `PARTIAL`; erro de leitura/escrita a torna `FAILED`.
Uma execução `PARTIAL`/`FAILED` nunca comprova cobertura. Valores ausentes não
são preenchidos. `co_documento` duplicado na partição também impede `SUCCESS`.

A ingestão calcula SHA-256 dos bytes de cada fragmento antes e depois do
processamento e registra hash conjunto, contagem de linhas, partição e esquema
na metadata imutável de `datasus_ingestion_runs`. Cada lote é confirmado em
transação; uma falha desfaz o lote corrente. Lotes anteriores permanecem
auditáveis numa execução `FAILED` e são ignorados pelo roteador. Raw, observação e projeção de cada
registro são atômicos via `OperationalPersistence`. Reexecutar a mesma partição
em uma nova execução preserva registros inalterados e adiciona observações;
mudanças arquivam a revisão anterior. Eventos estruturados registram apenas
IDs e contagens, sem payloads.

Se o processo for interrompido e deixar uma execução `RUNNING`, retome-a com:

```bash
python -m sus_explorer.data.persistence.ingest_r2 --year 2026 --month 5 --uf RS --resume-run-id 123
```

A retomada confirma origem, partição e hash idênticos e relê desde a primeira
linha com upsert idempotente. Uma execução terminal não pode ser retomada;
inicie outra execução. Um advisory lock impede dois processos deste fluxo de
ingestão sobre a mesma partição ao mesmo tempo.

## Seleção do executor

`003_partition_lookup_indexes.sql` acrescenta índices para localizar a execução
mais recente e contar raws de uma partição, sem alterar tabelas ou invariantes.

`POSTGRES_COUNT_ENABLED=0` mantém todas as consultas no R2. Com valor `1`, o
roteador avalia apenas `count` sem filtros de `year` + `month` + `uf`. Configure
essa opção antes de iniciar/reiniciar o Streamlit (o serviço é mantido em cache).
O roteador exige a execução mais recente `SUCCESS`, hash e número de fragmentos atuais iguais aos
registrados, contagem de linhas R2 igual à registrada, e igualdade entre
linhas recebidas, observações, raws correntes e projeções da revisão corrente.
Falta de partição não é contagem zero: sem origem R2 verificável, a consulta R2
retorna seu erro. Falta de cobertura, fonte alterada ou falha PostgreSQL levam
ao R2, sem usar números parciais do banco. Consultas anuais, filtradas,
agrupamentos, séries, latência e análise temporal permanecem no R2. O Gemini
não escolhe SQL nem recebe microdados.

O hash integral dos fragmentos em cada consulta elegível pode ser caro; este
opt-in é deliberadamente estreito. Antes de habilitar produção, validar o
esquema e unicidade de `co_documento` no R2 real, medir custo/latência de hash
por partição, preparar credenciais separadas de runtime/reader com TLS,
monitorar execuções `PARTIAL`/`FAILED`, testar recuperação de interrupções e
definir política de retenção/acesso dos payloads individuais. Planeje uma janela
de manutenção se `003` for aplicada sobre tabelas já volumosas, pois os índices
são criados dentro da transação de migration. Sem esses passos,
deixe `POSTGRES_COUNT_ENABLED=0`.

A migration habilita pgvector para evolução futura. Não há nesta versão criação
de embeddings, recuperação semântica ou RAG. Antes disso será necessário definir
fontes documentais, versão do modelo, política de reindexação, avaliação de
recall e regras que impeçam o LLM de transformar conteúdo recuperado em fonte
numérica autoritativa.

## Garantias do contrato

- `datasus_ingestion_runs` preserva identidade e metadados de proveniência. Uma
  execução terminada não pode ser alterada nem excluída.
- `datasus_raw_records` mantém a versão corrente; toda substituição arquiva o
  conteúdo anterior em `datasus_raw_record_revisions`.
- revisões e observações são append-only: triggers rejeitam `UPDATE` e `DELETE`;
- observações vinculam execução, registro, revisão e instante de coleta, e só
  podem ser inseridas enquanto a execução está `RUNNING`;
- a alteração do raw remove automaticamente qualquer projeção normalizada da
  revisão anterior. `OperationalPersistence.save_immunization()` grava raw e
  nova projeção numa transação única, portanto outros clientes veem ambos ou
  nenhum;
- consultas normalizadas também exigem igualdade entre `source_revision` e a
  revisão raw corrente, como defesa adicional;
- a conclusão da ingestão bloqueia a execução, serializa-se com writers e muda
  o estado para terminal na mesma transação;
- migrations são numeradas, ordenadas, executadas numa transação sob advisory
  lock e registradas com SHA-256. Alterar uma migration aplicada produz erro.

Payloads individuais, credenciais e PII não fazem parte dos eventos de log. Os
eventos registram somente tipo da operação, IDs técnicos, revisão, estado e
contagens.

## Modelo de ameaça e roles

Frontend, inputs de ingestão, conteúdo futuro de RAG e saída do LLM são tratados
como não confiáveis. O processo Python de runtime também pode ser comprometido;
por isso sua credencial não equivale à administração do banco.

A migration `002_security_hardening.sql` estabelece três roles estruturais
`NOLOGIN`, sem herança administrativa entre elas:

- `sus_explorer_migrator`: owner do schema, tabelas e funções de proteção. Só o
  principal de deployment que aplica migrations pode receber membership;
- `sus_explorer_runtime`: leitura e escrita apenas nas tabelas operacionais
  necessárias. Não possui objetos, não cria/altera/remove schema, não desabilita
  triggers, não escreve diretamente no histórico e não assume o migrator;
- `sus_explorer_reader`: `SELECT` explícito nas tabelas operacionais, sem escrita
  ou mutação de schema.

Cada processo usa um login próprio concedido a exatamente uma dessas roles. A
credencial de migration nunca é fornecida à aplicação, ao frontend ou ao LLM.
As funções internas executadas por triggers têm owner migrator, `SECURITY
DEFINER`, `search_path` fixo e `EXECUTE` revogado de `PUBLIC`; isso permite
arquivar revisões sem conceder escrita direta no histórico ao runtime.

O provisionamento de `CREATE EXTENSION vector` ainda está na migration inicial.
Em deployments que restringem extensões, essa etapa privilegiada deve ser
provisionada separadamente antes das migrations normais. A presença de pgvector
continua sendo somente fundação: embeddings e RAG não estão ativos.

## Conexão e inputs

As conexões configuram limites explícitos para conexão, statements, locks e
transações ociosas, além de `application_name` e `search_path` restrito ao schema
configurado mais `pg_catalog`. `POSTGRES_SSLMODE` aceita os modos nativos do
libpq; serviços remotos devem exigir `verify-full` e uma CA confiável. O default
`prefer` existe apenas para manter desenvolvimento local simples, não como
decisão implícita de produção.

Identificadores têm limites entre 128 e 1.024 caracteres conforme a função;
metadata aceita até 256 KiB; payload JSONB aceita até 4 MiB, profundidade máxima
32 e até 100 mil nós. Python rejeita tamanho, profundidade, valores não JSON e
NUL antes da transação; constraints PostgreSQL repetem os limites essenciais.

`error_summary` é sanitizado, convertido para uma linha e limitado a 2.048
caracteres. Passwords, tokens, assignments de secrets, URLs assinadas, e-mails,
CPF e valores secretos conhecidos são removidos. Tracebacks e exceções brutas
não devem ser persistidos.

O LLM não recebe credenciais PostgreSQL, não executa SQL e não é autoridade
sobre números. Mesmo uma saída maliciosa do modelo permanece fora desta
fronteira de persistência.

## Operação local

Copie `.env.example` para `.env`, escolha credenciais locais e execute:

```bash
docker compose up -d postgres
python -m sus_explorer.data.persistence.migrate
```

O Compose publica PostgreSQL somente em `127.0.0.1`. Importar a aplicação não
abre conexão nem aplica migrations.

## Testes

Os testes PostgreSQL são opt-in porque criam e removem schemas. Use
exclusivamente um banco descartável com pgvector:

```bash
SUS_EXPLORER_TEST_DB=1 python -m pytest tests/integration
```

Eles cobrem reaplicação e concorrência de migrations, checksum, rollback,
atomicidade raw/normalização, proteção do histórico e congelamento de ingestões.
Também criam logins descartáveis de runtime/reader e provam negativas de DDL,
escalation, trigger disabling, escrita no histórico e escrita após conclusão.
Os testes de integração R2→PostgreSQL geram Parquet local e verificam ingestão
inicial, lotes, reexecução, revisão, retomada, invalidade, rollback e roteamento
com contagens reais no banco. Não requerem nem escrevem no R2 remoto.

## Dependências, CI e controles do repositório

`requirements.txt` e `requirements-dev.txt` são as fontes de compatibilidade.
`constraints.txt` registra versões diretas revisadas usadas em CI e pode ser
aplicado localmente com:

```bash
python -m pip install -c constraints.txt -r requirements-dev.txt
```

Dependabot propõe atualizações semanais de Python e GitHub Actions para revisão;
o workflow fixa Actions por SHA e mantém `permissions: contents: read`.

Proteções administrativas não são alteradas por esta PR. Recomenda-se exigir PR
e o CI PostgreSQL para `master`, bloquear force push e exclusão da branch e
exigir revisão quando disponível. Dependency Review, CodeQL e secret scanning
dependem dos recursos/configuração do repositório; devem ser habilitados fora
desta PR quando suportados, sem ampliar permissões do workflow principal.
