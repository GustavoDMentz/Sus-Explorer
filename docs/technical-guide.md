# Guia técnico e operacional

## Instalação

Use Python 3.12 ou versão compatível com as dependências. Instale o ambiente de execução com `python -m pip install -c constraints.txt -r requirements.txt`. Para testes e ferramentas de migração, use `requirements-dev.txt`; `requirements-migration.txt` contém PyArrow, que não é necessário ao serviço normal.

Copie `.env.example` para `.env` e defina as credenciais PostgreSQL. Inicie PostgreSQL com pgvector e Ollama: `docker compose up -d postgres ollama`. Baixe os modelos com `docker compose exec ollama ollama pull qwen3:4b-instruct-2507-q4_K_M` e `docker compose exec ollama ollama pull qwen3-embedding:0.6b`. Verifique a dimensão real usando `python -m sus_explorer.check_local_ai` e aplique as migrations com `python -m sus_explorer.data.persistence.migrate`. A migration 007 exige vetor de 1024 dimensões. Execute `streamlit run app.py`.

O PostgreSQL é obrigatório para consultas analíticas e RAG. Uma instalação vazia não retorna doses até que competências completas sejam importadas. O banco mantém os dados em tabelas relacionais e os embeddings com pgvector. O modelo local só planeja e explica; Python/SQL calculam os números. [Detalhes de arquitetura](architecture.md) e [IA local](local-ai-rag.md).

## Importação e atualização

Para um ZIP oficial nacional, baixe o recurso mensal listado no portal e importe uma UF sem extrair o CSV: `python -m sus_explorer.data.persistence.ingest_csv ARQUIVO.zip --year 2026 --month 1 --uf AC --resource-id 7a23edf5-0315-48f6-88a3-015ba3ac51af`. O importador reconhece Latin-1 e ponto e vírgula para ZIPs; verifique o recurso e o identificador no [portal oficial](https://dadosabertos.saude.gov.br/dataset/doses-aplicadas-pelo-programa-de-nacional-de-imunizacoes-pni-2026/resource/7a23edf5-0315-48f6-88a3-015ba3ac51af). Cada execução filtra `sg_uf_estabelecimento`, valida a competência, calcula hash do arquivo, grava em lotes, retoma a mesma origem após interrupção e só marca `SUCCESS` após reconciliar contagens. O download pode ser feito para um diretório com espaço suficiente; o código não extrai o CSV em disco.

Para importar o espelho legado sem mantê-lo no fluxo de consulta, instale `requirements-migration.txt`, configure apenas as variáveis `LEGACY_R2_*` de `.env.legacy-r2.example`, gere o manifesto com `python -m sus_explorer.data.persistence.legacy_inventory --output audit/legacy_inventory.json` e processe lotes explícitos com `python -m sus_explorer.data.persistence.migrate_legacy_partitions --manifest audit/legacy_inventory.json --start-at 0 --limit 1`. Revise status e contagens em `datasus_ingestion_runs`. Nenhum comando remove objetos do bucket.

## Testes e limites

`python -m pytest tests -q` executa contratos locais; os testes PostgreSQL exigem `SUS_EXPLORER_TEST_DB=1` e um banco descartável cujo nome termina em `_test`. O canário Ollama/RAG real está em `tests/e2e/test_local_rag.py` e exige também `SUS_EXPLORER_RAG_E2E=1`. Compare agregados PostgreSQL com referências independentes ou com o leitor legado durante a migração. O catálogo da interface mostra a última execução por competência e não interpreta ausência como zero.

A documentação em `development_journal.md`, `pr_register.md`, `test_audit.md` e `refactor_findings.md` é histórica e pode descrever a arquitetura anterior. Não use esses registros como instruções de instalação atuais.
