# Persistência operacional PostgreSQL

## Papel no sistema

PostgreSQL complementa o backend analítico Parquet/R2. Ele registra operações
de ingestão, proveniência da fonte, representações JSONB, histórico de revisões
e projeções normalizadas. As consultas analíticas existentes continuam usando
Parquet/R2 e não fazem fallback para o banco.

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
