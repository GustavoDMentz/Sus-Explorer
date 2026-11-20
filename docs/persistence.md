# Persistência PostgreSQL

As migrations numeradas em `sus_explorer/data/persistence/migrations/` são aplicadas por `python -m sus_explorer.data.persistence.migrate`, com verificação SHA-256 e lock transacional. A migration 001 habilita pgvector e cria os registros operacionais; 004/005 armazenam histórico opcional; 007 cria a base documental; 008 indexa o identificador de competência para o executor analítico. Não edite migrations já aplicadas.

## Dados estruturados

`datasus_ingestion_runs` controla cada ingestão por origem e competência. `datasus_raw_records`, revisões e observações preservam o histórico de fonte. `immunization_records` mantém projeções estruturadas e vincula cada evento ao registro bruto. O executor analítico usa apenas uma competência com última execução `SUCCESS` e contagens reconciliadas. Dados parciais ou ausentes são indisponíveis, nunca zero automático. O JSONB bruto guarda os campos originais necessários para filtros e auditoria; o modelo relacional oferece identidade, datas, vacina e geografia. Consultas extensas exigem avaliação de índices e dimensionamento com dados reais.

## Migração legada

O inventário de 08/11/2026 contém 2.187 partições ano/mês/UF. Uma checagem HTTP HEAD de 81 ZIPs mensais oficiais OpenDataSUS, correspondentes a 2020-01–2026-09, retornou HTTP 200 para todos; o tamanho comprimido total informado pelos cabeçalhos foi 215.204.859.439 bytes. O arquivo oficial contém CSV nacional, que o importador percorre em streaming e filtra pela UF. Esse probe prova disponibilidade do arquivo mensal, não que cada UF tenha registros, nem sua contagem. O relatório `audit/migration_coverage_2026-11-08.json` separa execução concluída, falha e pendência com contagens conhecidas ou nulas. A ingestão valida schema, `co_documento`, hash da origem antes/depois, contagens observadas/projetadas e replay idempotente da mesma execução. Uma execução `PARTIAL` ou `FAILED` não é selecionada pelo serviço. A carga integral ainda precisa de um destino PostgreSQL com espaço dimensionado para os dados, índices e WAL. Os leitores R2 estão fora da aplicação normal; nenhum bucket ou origem é alterado.

## Documentos e embeddings

`knowledge_documents` guarda título, referência, hash e identidade do modelo. `knowledge_chunks` contém trechos e vetores `vector(1024)`; `knowledge_indexing_attempts` guarda resultados de indexação sem conteúdo sensível. A reindexação prepara todos os vetores antes da troca transacional. A recuperação filtra pelo nome e digest do modelo, fonte, tipo e metadados. A busca exata por cosseno é a escolha atual para um corpus pequeno; HNSW depende de medição.

## Segurança operacional

Use papéis distintos para migrations, ingestão, histórico e leitura analítica: o guia está em [postgres-roles.md](postgres-roles.md), e os perfis `reader`, `ingest`, `history` e `migrator` já são usados pelo código. Restrinja a porta do PostgreSQL à rede necessária e configure TLS conforme o ambiente. Mantenha backup, teste restauração e monitore volume, RAM, tempo de consulta e crescimento de índices antes de importar centenas de milhões de registros. As credenciais de produção não pertencem ao Git.

## Reimportação de meses republicados

O Ministério republica os ZIPs mensais com frequência (em novembro de 2026, os meses de janeiro a setembro foram atualizados). `ingest_csv` trata cada arquivo como um **snapshot** identificado por `snapshot_id` (recurso, partição e os 16 primeiros caracteres do SHA-256 do arquivo), com o checksum completo e a contagem de linhas nos metadados da execução.

- **Troca atômica.** O snapshot inteiro é gravado em **uma transação**. Enquanto ela não for confirmada, o app continua servindo o snapshot anterior; quando for, tudo muda de uma vez. Qualquer falha desfaz tudo (registros, revisões, observações) e o snapshot anterior continua valendo; a execução fica `FAILED`. O custo é que uma interrupção reinicia a leitura do arquivo do começo.
- **Registros removidos.** Um registro que o novo snapshot não traz continua guardado (o histórico é imutável), mas deixa de ser servido: o executor lê apenas o que a execução bem-sucedida mais recente **observou**.
- **Reconciliação por etapas.** Linhas lidas = observações = projeções; as contagens (lidas, observadas, projetadas, registros guardados e aposentados) vão para o log `csv_ingestion_reconciled`. Um `co_documento` repetido no arquivo é recusado com a quantidade de duplicatas e nada é confirmado.
- **Execuções órfãs.** Se o processo morre no meio, a execução fica `RUNNING`. Como o importador mantém um *lock* da partição durante todo o trabalho, quem consegue o lock sabe que não há dono vivo: a próxima importação da partição fecha a órfã como `FAILED` ("Orphaned run closed") e começa uma nova. O expurgo também recusa partições com execução em andamento.
- **Disponibilidade.** A leitura usa a última execução **bem-sucedida** de cada partição; uma execução em andamento ou falha nunca tira do ar o que já estava sendo servido.
