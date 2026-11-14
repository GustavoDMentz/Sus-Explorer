# Validação da migração para PostgreSQL, pgvector e Ollama — 08/11/2026

## Fluxo implementado

`Streamlit → SUSExplorer → Ollama (QueryPlan validado) → PostgresQueryExecutor → PostgreSQL → pgvector quando houver intenção documental → Ollama → resposta com proveniência`.

O serviço normal não importa `pyarrow` e não configura cliente R2. O SDK Google GenAI, a chave Gemini e os workflows exclusivos de R2 saíram do caminho operacional. O acesso R2/Parquet foi isolado nas ferramentas de migração e auditoria, com credenciais explícitas `LEGACY_R2_*`. Não há fallback do executor PostgreSQL para R2.

## Dados e persistência verificados

- Inventário somente de leitura do espelho histórico SI-PNI: 2.187 partições ano/mês/UF em `audit/legacy_r2_inventory_2026-11-08.json`. O inventário não contém contagem de linhas de cada partição.
- A checagem sem credenciais dos recursos OpenDataSUS encontrou HTTP 200 para 81 ZIPs mensais (2020-01 a 2026-09), totalizando 215.204.859.439 bytes comprimidos. Os cabeçalhos não informam contagens por UF. Evidência detalhada em `audit/opendatasus_monthly_inventory_2026-11-08.json`.
- Partição real `ano=2020/mes=01/uf=AC`: 16.275 registros lidos do espelho e 16.275 linhas em `datasus_raw_records` e `immunization_records` no PostgreSQL descartável. Execução `SUCCESS`, sem duplicatas detectadas, com hash de origem registrado.
- Partição oficial `ano=2026/mes=01/uf=AC`: 81.061 linhas no CSV nacional filtradas por `sg_uf_estabelecimento=AC`; 81.061 registros recebidos/inseridos, zero atualizados. A contagem da consulta SQL e a reconciliação de ingestão são 81.061. SHA-256 do ZIP registrado no run de ingestão.
- Comparação antiga/nova para essa partição: total 16.275; sexo F 8.415 e M 7.860; código de vacina 9 com 749; latência com `n_valid=16.275`, mediana 1.191, p90 1.458 e p95 1.760 dias; série 2020-01 com 16.275. Filtros de município, idade e texto de vacina, agrupamentos e diferença temporal de primeira ordem também coincidiram.
- Base documental de teste: 3 documentos locais reais, 19 trechos e embeddings de 1.024 dimensões persistidos em pgvector. Busca semântica e resposta gerada com Ollama foram executadas em banco descartável.

## Verificações executadas

- PostgreSQL 17 + pgvector 0.8.6 em contêiner descartável; migrations 001–008 aplicadas.
- Ollama com `qwen3:4b-instruct-2507-q4_K_M` e `qwen3-embedding:0.6b`; verificação real de disponibilidade e dimensão dos embeddings.
- Suíte: 467 testes aprovados, 2 testes externos deselecionados por padrão. Inclui integração PostgreSQL com banco descartável.
- Teste RAG real opcional: 1 aprovado, incluindo indexação, busca vetorial, resposta e fonte.
- Teste ponta a ponta Streamlit + Ollama + PostgreSQL: 1 aprovado em 145,62 s sobre a partição real AC/01-2020, com 16.275 doses e sem chaves Gemini/R2.
- `git diff --check` sem erros de whitespace. O banco piloto continha 16.275 registros estruturados, 3 documentos e 19 trechos no momento da conferência.

## Limites para declarar conclusão

A migração **não está integralmente concluída**. A auditoria por competência registra 2 partições com ingestão válida em banco descartável, 2.185 pendentes e nenhuma parcial/falha. O resumo, as contagens conhecidas, hashes e motivos por partição estão em `audit/migration_coverage_2026-11-08.json`. Todas as 81 fontes mensais responderam HTTP 200, mas a contagem por UF permanece desconhecida nas partições pendentes. Nenhuma carga foi aplicada a um PostgreSQL permanente. Os ZIPs somam 215,2 GB comprimidos, enquanto o banco local de teste é descartável e o disco de dados Docker não comporta a carga integral. Não foram apurados o total de linhas nem o espaço PostgreSQL necessário das partições restantes.

A estrutura atual conserva o payload original em JSONB e projeta os campos centrais tipados em `immunization_records`; alguns agrupamentos ainda extraem dimensões do JSONB. Índices e particionamento devem ser avaliados com volumes representativos antes da carga nacional. O teste ponta a ponta foi via `AppTest`, não em navegador real. O consumo observado do contêiner Ollama durante inferência ficou perto de 5,9 GiB, acima da hipótese de 4 GiB para a pilha inteira.

Nenhum bucket, dado de origem, volume persistente ou credencial externa foi apagado. Valores de credenciais antes embutidos no código foram removidos. A busca pelo histórico Git (`git log --all -G 'r2_secret_key|r2_access_key'`) encontrou referências em commits de 2026-09-22 e 2026-09-26 e nos commits `229698e`, `b54f423` e `83a2d8d` de 2026-10-19. Os valores foram omitidos. O responsável pelo acesso deve invalidar/rotacionar essas credenciais; a limpeza do histórico remoto requer procedimento coordenado e ainda não foi feita. A carga histórica pode usar os ZIPs oficiais verificados, sem reutilizar credenciais R2.
