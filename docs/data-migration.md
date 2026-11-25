# Migração incremental dos dados

## Fluxo operacional

O arquivo oficial é mensal e nacional. O job incremental baixa uma competência, retoma um `.part` compatível por HTTP Range, confere tamanho e SHA-256, importa as UFs sequencialmente e registra um checkpoint JSON após cada partição reconciliada.

```bash
python -m sus_explorer.data.remote.opendatasus_catalog \
  --years 2026 --manifest audit/opendatasus-pni.json --write

python -m sus_explorer.data.remote.incremental_import \
  --catalog audit/opendatasus-pni.json \
  --year 2026 --month 1 \
  --staging D:/sus-staging \
  --ufs AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO \
  --delete-after-success
```

`--delete-after-success` remove apenas o ZIP criado pelo próprio job e somente depois de todas as UFs selecionadas terminarem em `SUCCESS`. Um arquivo que já existia no staging nunca é apagado. Falhas preservam o ZIP, o `.part` ou o checkpoint para diagnóstico e retomada.

## Garantias

- uma competência no staging por execução;
- retomada somente quando URL, tamanho e ETag correspondem ao mesmo snapshot;
- hash SHA-256 calculado antes da ingestão;
- leitura em lotes sem extrair o CSV em disco;
- lock PostgreSQL por partição;
- unicidade por origem, partição e `co_documento`;
- transação atômica por UF e reconciliação de observações/projeções;
- reexecução idempotente do mesmo snapshot;
- snapshot anterior continua servível durante falha de reimportação.

## Dimensionamento

O total comprimido das fontes mede transferência histórica, não staging simultâneo. O staging precisa comportar o maior ZIP mensal, seu `.part` durante a retomada e margem de filesystem. Meça separadamente:

1. tamanho máximo mensal comprimido;
2. crescimento das tabelas e TOAST após uma amostra representativa;
3. índices com `pg_relation_size`/`pg_indexes_size`;
4. pico de WAL durante uma partição;
5. margem para vacuum, manutenção, logs e falhas.

Não há estimativa comprovada para o PostgreSQL completo. Extrapole somente depois de importar competências representativas e registre amostra, fórmula e margem. O job não inicia todas as competências de uma vez.

No manifesto `audit/opendatasus-pni-2026-11-25.json`, a maior competência observada foi 2021-09 com 7.533.194.223 bytes (7,016 GiB). Esse é um valor medido do ZIP, não o orçamento completo de staging: filesystem, arquivo parcial e margem continuam necessários. Tabelas, índices e WAL permanecem desconhecidos até uma carga representativa.

Após carga, execute `python -m sus_explorer.data.persistence.semantic_audit` e gere a cobertura com `python -m scripts.report_migration_coverage` usando os argumentos exigidos pelo comando.
