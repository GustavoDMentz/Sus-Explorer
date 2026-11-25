# Arquitetura do SUS Explorer

O fluxo ativo é Streamlit (`app.py`) → `SUSExplorer.ask()` → planejador determinístico ou Ollama → `QueryPlan` validado → `PostgresQueryExecutor` → tabelas relacionais PostgreSQL → agregados Python/SQL → recuperação documental opcional em pgvector → Ollama → resultado com proveniência analítica e fontes documentais separadas.

## Dados analíticos

`datasus_ingestion_runs` registra origem, hash, competência, contagens e estado. `datasus_raw_records` preserva o conteúdo original e seu histórico; `immunization_records` mantém a projeção estruturada de identidade, vacina, dose, data e local. O executor seleciona somente a última ingestão `SUCCESS` de cada competência cuja contagem corresponde à origem declarada. Ausência ou ingestão parcial não vira zero. Contagens, agrupamentos, séries e latência são SQL parametrizado; diferenças temporais e percentuais continuam no módulo Python existente. O modelo de linguagem não produz SQL nem calcula doses.

O catálogo do Streamlit consulta o PostgreSQL. A operação normal não importa `pyarrow`, não abre Parquet e não usa credenciais R2. Os módulos `pni.py`, `hybrid.py`, `data/remote/r2.py` e `data/persistence/ingest_r2.py` permanecem como ferramentas legadas isoladas para migração e comparação enquanto o inventário ainda não estiver integralmente migrado.

## Conhecimento documental

A migration 007 cria `knowledge_documents`, `knowledge_chunks` (`vector(1024)`) e `knowledge_indexing_attempts`. Arquivos públicos escolhidos pelo operador são divididos em trechos, transformados em embeddings pelo Ollama e gravados em uma transação por documento. A busca por cosseno filtra fonte e identidade do modelo por nome mais digest. Perguntas analíticas simples dispensam busca vetorial; perguntas interpretativas, temporais ou que mencionam documentação recuperam evidências. O Ollama sintetiza uma resposta em português a partir dessas evidências e, quando disponível, do agregado já calculado; não calcula os indicadores. O backend acrescenta referências `arquivo#chunk-N` vindas das linhas persistidas e a interface mostra os trechos consultados. Instruções dentro de documentos são tratadas como conteúdo não confiável. Sem evidências verificáveis, a resposta documental declara contexto insuficiente.

## Fontes e migração

A fonte histórica ativa antes desta mudança era o espelho `healthbr-data/sipni/microdados/` no Cloudflare R2. O caminho atual usa os ZIPs mensais oficiais do OpenDataSUS. `incremental_import.py` mantém uma competência no staging, retoma o download e importa UFs sequencialmente; `ingest_csv.py` filtra a UF e grava em lotes. O leitor R2 permanece isolado para auditoria/migração legada. Consulte [fontes](data-sources.md), [migração](data-migration.md), [banco](database.md) e [RAG](rag.md).

## Limites

O repositório não possui API REST separada: o frontend é Streamlit. O índice documental tem somente o escopo de documentação pública do projeto, sem upload ou permissões por organização. O volume integral de microdados exige dimensionamento de disco, RAM, índices e tempo de importação; a validação de uma partição não comprova migração completa nem equivalência de todas as consultas.
