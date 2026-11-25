# Solução de problemas

Comece com:

```bash
python -m sus_explorer.diagnose
```

## `.env` ausente

Copie `.env.example`, preencha senhas reais e mantenha o arquivo fora do Git. O Compose recusa inicialização sem as cinco senhas exigidas.

## PostgreSQL indisponível

Confira `docker compose ps`, porta, host, SSL e perfil usado. O diagnóstico diferencia falha de conexão de ausência de pgvector/migrations. Não aponte testes para banco persistente: use nome terminado em `_test` e `SUS_EXPLORER_TEST_DB=1`.

## Ollama indisponível ou modelo ausente

Confira `/api/tags`, `OLLAMA_BASE_URL` e execute os `ollama pull` documentados. Rode `check_local_ai` antes de indexar. Não mude a dimensão para contornar erro de modelo; reindexação precisa ser explícita.

## Download interrompido

Reexecute `incremental_import` com o mesmo catálogo e staging. O `.part` só é retomado se URL, tamanho e ETag forem os mesmos. Divergência preserva o arquivo e exige decisão manual para evitar misturar snapshots.

## Pouco espaço

Orce separadamente staging de uma competência, PostgreSQL, índices, WAL e margem. Reduzir o staging não reduz o banco definitivo. Não use os 218,3 GB totais como staging simultâneo do pipeline sequencial.

## Competência sem resultado

Consulte a aba de disponibilidade e `datasus_ingestion_runs`. Ausência, falha, expurgo ou contagem não reconciliada deixam a partição indisponível; não representam zero doses.
