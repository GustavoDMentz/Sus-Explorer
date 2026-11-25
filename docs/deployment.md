# Implantação e operação

## Execução local

A implantação local suportada usa Docker Compose e dispensa Python no host. Configure os segredos no `.env` conforme [installation.md](installation.md) e inicie toda a stack com:

```bash
docker compose up -d --build
```

Compose controla as dependências de saúde e conclusão: `postgres` e `ollama` iniciam primeiro; `migrate` e `ollama-init` precisam concluir; `index-docs` termina a preparação documental; então `app` atende em `127.0.0.1:8501`. A aplicação conecta como `reader`. Não publique diretamente PostgreSQL ou Ollama. A rede interna Compose usa os aliases `postgres` e `ollama`; exceções de transporte sem TLS são limitadas a esses peers internos.

Use `docker compose ps` e `docker compose logs migrate index-docs app` para acompanhar a inicialização. Migrations são numeradas, protegidas por checksum e lock transacional. O indexador mantém documentos e chunks existentes quando conteúdo, digest do embedding e configuração de chunking/dimensão continuam compatíveis.

Os volumes nomeados `postgres_data_v2` e `ollama_data` preservam dados e modelos. `docker compose down` preserva volumes; `docker compose down -v` os apaga. Importe dados SI-PNI apenas por operação explícita conforme [data-migration.md](data-migration.md); a inicialização automática não executa a migração histórica.

## Hosts compartilhados ou remotos

Para acesso remoto, use proxy TLS e autenticação; não publique PostgreSQL ou Ollama diretamente. Configure conexão PostgreSQL externa com TLS e habilite acesso remoto ao Ollama somente com HTTPS e a opção explícita documentada em [configuration.md](configuration.md). Monitore disco, WAL, conexões, latência, recuperação e inferência.

Backups precisam incluir banco e chaves necessárias aos históricos cifrados. Teste restauração. O staging de ZIPs pode ser efêmero; checkpoints e trilha de ingestão devem ser preservados.
