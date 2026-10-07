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
