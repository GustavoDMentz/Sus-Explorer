# Arquitetura do SUS Explorer

O fluxo ativo é Streamlit (`app.py`) → `SUSExplorer.ask()` → planejador determinístico ou Ollama → `QueryPlan` validado → `PostgresQueryExecutor` → tabelas relacionais PostgreSQL → agregados Python/SQL → recuperação documental opcional em pgvector → Ollama → resultado com proveniência analítica e fontes documentais separadas.

## Dados analíticos

`datasus_ingestion_runs` registra origem, hash, competência, contagens e estado. `datasus_raw_records` preserva o conteúdo original e seu histórico; `immunization_records` mantém a projeção estruturada de identidade, vacina, dose, data e local. O executor seleciona somente a última ingestão `SUCCESS` de cada competência cuja contagem corresponde à origem declarada. Ausência ou ingestão parcial não vira zero. Contagens, agrupamentos, séries e latência são SQL parametrizado; diferenças temporais e percentuais continuam no módulo Python existente. O modelo de linguagem não produz SQL nem calcula doses.

O catálogo do Streamlit consulta o PostgreSQL. A operação normal não importa `pyarrow`, não abre Parquet e não usa credenciais R2. Os módulos `pni.py`, `hybrid.py`, `data/remote/r2.py` e `data/persistence/ingest_r2.py` permanecem como ferramentas legadas isoladas para migração e comparação enquanto o inventário ainda não estiver integralmente migrado.

## Conhecimento documental

A migration 007 cria `knowledge_documents`, `knowledge_chunks` (`vector(1024)`) e `knowledge_indexing_attempts`. Arquivos públicos escolhidos pelo operador são divididos em trechos, transformados em embeddings pelo Ollama e gravados em uma transação por documento. A busca por cosseno filtra fonte e identidade do modelo por nome mais digest. Perguntas analíticas simples dispensam busca vetorial; perguntas interpretativas e temporais podem recuperar documentação. Para essas perguntas, o backend apresenta somente excertos literais com identificador `arquivo#chunk-N`; não pede ao gerador para parafrasear documentos. Sem excertos verificáveis, a resposta documental declara contexto insuficiente. Documentos recuperados são tratados como dados não confiáveis.

## Fontes e migração

A fonte histórica ativa antes desta mudança era o espelho `healthbr-data/sipni/microdados/` no Cloudflare R2, organizado por ano/mês/UF. O inventário de 08/11/2026 encontrou 2.187 partições. Uma checagem HTTP sem credenciais encontrou 81 arquivos mensais oficiais OpenDataSUS, de 2020-01 a 2026-09, com 215,2 GB comprimidos no total. Isso comprova disponibilidade dos ZIPs, não a contagem por UF nem a carga integral no PostgreSQL. `ingest_csv.py` lê o CSV dentro do ZIP, filtra a UF e carrega em lotes. O leitor R2 permanece isolado apenas para validação pontual; credenciais históricas potencialmente comprometidas não são usadas. Nenhum bucket é modificado ou apagado. Consulte [persistência](persistence.md) e [IA local](local-ai-rag.md).

## Limites

O repositório não possui API REST separada: o frontend é Streamlit. O índice documental tem somente o escopo de documentação pública do projeto, sem upload ou permissões por organização. O volume integral de microdados exige dimensionamento de disco, RAM, índices e tempo de importação; a validação de uma partição não comprova migração completa nem equivalência de todas as consultas.
