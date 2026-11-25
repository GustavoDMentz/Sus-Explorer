# Instalação

## Ambiente recomendado

- Linux com Python 3.12, alvo do CI e do `requirements-lock.txt`.
- Docker Engine com Compose para PostgreSQL 17/pgvector e Ollama, ou serviços equivalentes instalados no host.
- Armazenamento dimensionado separadamente para staging, tabelas, índices, WAL e margem operacional.

O código e as dependências diretas também foram exercitados em Windows/Python 3.13, mas o lock reproduzível é gerado para Linux/Python 3.12.

## Preparação

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-lock.txt
cp .env.example .env
```

No PowerShell, ative com `.\.venv\Scripts\Activate.ps1` e copie com `Copy-Item .env.example .env`.

Preencha as senhas reais no `.env`; não copie valores de exemplo para produção. Inicie os serviços:

```bash
docker compose up -d postgres ollama
docker compose exec ollama ollama pull qwen3:4b-instruct-2507-q4_K_M
docker compose exec ollama ollama pull qwen3-embedding:0.6b
python -m sus_explorer.diagnose
python -m sus_explorer.check_local_ai
python -m sus_explorer.data.persistence.migrate
streamlit run app.py
```

`check_local_ai` deve confirmar 1.024 dimensões antes da migration documental. Uma mudança de modelo ou dimensão exige decisão explícita e reindexação.

Consulte [configuration.md](configuration.md) para variáveis, [data-migration.md](data-migration.md) para importar dados e [troubleshooting.md](troubleshooting.md) para falhas de inicialização.
