# Configuração

Use `.env.example` como contrato. `.env` é ignorado pelo Git.

## Grupos principais

| Grupo | Variáveis principais | Regra |
| --- | --- | --- |
| Ollama | `OLLAMA_BASE_URL`, `OLLAMA_CHAT_MODEL`, `OLLAMA_EMBEDDING_MODEL`, timeouts | Endpoint remoto exige opt-in e HTTPS |
| RAG | `RAG_EMBEDDING_DIM`, `RAG_TOP_K`, `RAG_MIN_SIMILARITY`, limites de chunk/contexto | Dimensão deve corresponder ao índice |
| PostgreSQL | host, porta, banco, schema, SSL e timeouts | Serviço remoto exige TLS `require` ou mais forte |
| Papéis | credenciais `MIGRATOR`, `INGEST`, `HISTORY`, `READER` | Ative `POSTGRES_REQUIRE_PROFILES=1` após configurar todos |
| Históricos | `POSTGRES_HISTORY_ENABLED`, `ANALYTICAL_HISTORY_ENABLED`, chave | Desligados por padrão; chave fica fora do Git |

## Diagnóstico

```bash
python -m sus_explorer.diagnose \
  --temporary-gib <maior-zip-mensal-medido> \
  --postgres-gib <tabelas-extrapoladas-de-amostra> \
  --indexes-gib <indices-extrapolados-de-amostra> \
  --wal-gib <pico-medido-com-margem> \
  --margin-gib <margem-operacional-planejada>
```

Os valores são entradas do operador, baseadas em medições ou planejamento da infraestrutura. O comando não transforma o volume total dos 83 ZIPs em requisito temporário: o pipeline incremental conserva apenas uma competência no staging. PostgreSQL, índices e WAL são permanentes ou operacionais e precisam de orçamento próprio.

O diagnóstico é somente leitura. Ele verifica Python, dependências, presença do `.env`, espaço livre, conexão PostgreSQL, pgvector, migrations, Ollama, modelos e dimensão do embedding.
