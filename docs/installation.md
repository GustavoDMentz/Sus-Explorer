# Instalação

## Inicialização local com Docker Compose

Requisitos: Docker Engine com Docker Compose v2 e armazenamento suficiente para os dados PostgreSQL e modelos Ollama. Python não precisa estar instalado no computador.

1. Copie `.env.example` para `.env`.
2. Configure senhas fortes e exclusivas em `POSTGRES_PASSWORD`, `POSTGRES_MIGRATOR_PASSWORD`, `POSTGRES_INGEST_PASSWORD`, `POSTGRES_HISTORY_PASSWORD` e `POSTGRES_READER_PASSWORD`. Não compartilhe nem versione o `.env`.
3. Na pasta do projeto, execute:

```bash
docker compose up -d --build
```

Quando a inicialização terminar, abra <http://localhost:8501>. O Compose aguarda o healthcheck do PostgreSQL, executa o módulo `sus_explorer.data.persistence.migrate` como perfil `migrator`, aguarda o `ollama-init` baixar os modelos configurados, indexa `docs/architecture.md`, `docs/data-sources.md` e `docs/analytics.md` e só então inicia o Streamlit como perfil `reader`. Migrations usam checksum, ordem e lock transacional; uma falha impede os serviços dependentes de iniciar. O perfil `migrator` é superusuário porque a migration imutável 002 altera atributos de papéis; sua senha não é fornecida ao container `app`.

Os volumes nomeados `postgres_data_v2` e `ollama_data` preservam banco e modelos entre reinicializações. A indexação ignora documentos sem mudança de conteúdo, digest do modelo e configuração de chunks/dimensão. A importação histórica dos ZIPs SI-PNI não é disparada pela inicialização.

Verifique o estado com `docker compose ps` e mensagens com `docker compose logs migrate index-docs app`. Para reiniciar a aplicação use `docker compose restart app`. Não use `docker compose down -v` se precisar preservar os dados.

Consulte [configuration.md](configuration.md), [data-migration.md](data-migration.md) para importação explícita de dados e [troubleshooting.md](troubleshooting.md) para falhas de inicialização.
