# Auditoria da suíte de testes — 17/10/2026

Este é um registro da revisão do checkout local, não uma certificação de serviços externos. O [README](../README.md) é a referência operacional. O ponto de partida tinha **397 casos coletados**: 385 aprovados e 12 PostgreSQL pulados nesta máquina. Ao final, `pytest tests` selecionou 402 dos 403 casos coletados: **402 aprovados, 0 pulados, 1 externo deselecionado e 0 falhas** com PostgreSQL descartável. Sem Docker, foram **390 aprovados, 12 pulados e 1 deselecionado**. A árvore já continha alterações locais de implementação, testes, migrations 004 e documentação; elas foram preservadas.

## Método e limites

Foram inspecionados os 20 arquivos unitários, os 2 arquivos PostgreSQL de integração, fixtures, parametrizações, mocks, AppTest, fluxos de consulta/ingestão e os três workflows. As conclusões abaixo distinguem comportamento exercitado de fronteiras substituídas. `pytest --collect-only`, execução completa, execução por marcador, cobertura de branches e uma mutação controlada foram usados para confrontar as hipóteses. O Docker daemon estava inicialmente parado; após iniciá-lo, o script criou e removeu um contêiner PostgreSQL temporário. Nenhuma operação foi feita no banco persistente nem no R2/Gemini reais.

Os números por arquivo representam casos coletados, inclusive parametrizações. **Aprovação de um caso unitário não comprova que a origem, o modelo ou o banco remoto estejam corretos.**

## Inventário e julgamento por grupo

| Grupo de testes | Casos atuais | Comportamento realmente validado | Limite, decisão |
| --- | ---: | --- | --- |
| `unit/test_audit_ms.py` | 23 | Comparação sintética por chave, totais, erros, publicação atômica | Não lê MS/R2 real; manter por invariantes fortes. |
| `unit/test_gemini_native_schema.py` | 15 | Schema enviado ao SDK simulado, parsing/limites, retry de saída inválida, falha de transporte | A saída simulada já contém o plano desejado; não prova compreensão do português pelo Gemini. Mantido e ampliado. |
| `unit/test_hybrid_ingestion.py` | 6 | Roteamento e snapshot sobre Parquet local; contadores SQL simulados | Não comprova constraints/transações do banco; manter junto à integração PostgreSQL. |
| `unit/test_manifest.py` | 9 | Manifest, serialização, corrupção, escrita atômica | Não prova integridade do bucket; manter. |
| `unit/test_operational_logging.py` | 11 | Envelope, redação e falha segura de log | Não cobre transporte externo; manter. |
| `unit/test_paths.py` | 3 | Localização e tipos de caminhos | `test_paths_are_path_instances` é asserção de baixo valor isolada; manter como smoke barato, sem usá-la como evidência funcional. |
| `unit/test_percentage.py` | 15 | Resultados exatos MoM, zero, lacuna, precisão e apresentação | Forte para fórmula; mutação de escala foi detectada. Manter. |
| `unit/test_persistence_contract.py` | 12 | Validação/sanitização e alguns contratos de conexão | `test_migration_declares_database_enforced_invariants` procura palavras no SQL: passaria mesmo com trigger incorreta. Somente integração real comprova execução; manter como guarda textual secundária. |
| `unit/test_provenance.py` | 2 | Instanciação de dataclasses hoje não usadas no fluxo ativo | Baixo valor para regras de negócio; manter até decisão sobre o módulo, sem contar como cobertura do pipeline. |
| `unit/test_query_history.py` | 3 | Projeção sem texto livre e sucesso/falha de história com persistência simulada | Escrita/leitura real dependem de PostgreSQL; manter. |
| `unit/test_query_integrity.py` | 29 | Rejeição diária, limites/intervalos e revalidação antes da origem | Forte para plano local; não prova interpretação do Gemini. Manter. |
| `unit/test_seasonal_context.py` | 11 | Resumo de volumes, picos, lacunas e apresentação | Não estabelece sazonalidade clínica; manter. |
| `unit/test_streamlit_app.py` | 17 | AppTest de submissão, sessão, operações, erro e proveniência | Vários cenários injetam resultado pronto. `test_existing_operations_render_without_backend_initialization` antes só exigia ausência de exceção; agora verifica valores/cards/gráfico/tabela. Mantido e ampliado. |
| `unit/test_streamlit_provenance.py` | 15 | Classificação visual, contraste, rótulos e ausência de enriquecimento inventado | Não é captura de navegador; manter. |
| `unit/test_temporal_analytics.py` | 45 | Diferenças exatas, calendário, tipos, nulos e proveniência | Cobre bem função pura, sem provar dados externos. Manter. |
| `unit/test_temporal_query.py` | 90 | Validação do adaptador, filtros, erros e orquestração com origem/modelo simulados | O antigo nome `end_to_end_with_mocks` prometia mais do que executava; renomeado. O teste de intenção injeta o plano esperado e só confirma contrato/prompt, não reconhecimento real. Manter pelo contrato local. |
| `unit/test_transform.py` | 39 | Normalização, idade e partição com exemplos variados | São transformações do cubo, não o caminho remoto ativo; manter. |
| `unit/test_vaccine_filter.py` | 7 | União sem duplicação, filtros e contagens sobre backend local com vocabulário substituído | Não valida catálogo remoto atualizado; manter. |
| `unit/test_year_interval.py` | 13 | Expansão explícita de anos e casos ambíguos | Não comprova saída do Gemini real; manter. |
| `unit/test_yoy.py` | 23 | Calendário, referência, filtros, nulos, precisão e PyArrow local em um caso | Manter; série histórica real ainda não verificada. |
| `integration/test_postgres_foundation.py` | 8 | Em banco descartável: migrations, transações, revisões, privilégios e histórico reaberto | Executados com PostgreSQL 17/pgvector temporário e aprovados; não provam operação em produção. Manter. |
| `integration/test_r2_postgres_ingestion.py` | 4 | Em banco descartável: Parquet local → ingestão, revisão, parcial, rollback, retomada e roteamento | R2 e `LocalSource.execute` são substituídos; isso prova persistência/roteamento local, não R2 real. Executados e aprovados. Manter. |
| `integration/test_local_query_pipeline.py` | 2 | Parquet local → PyArrow real → plano/serviço → cálculo → AppTest; também count/group/latency com filtros | Gemini transport e filesystem remoto são substituídos; integração B, não E2E externo. Adicionado. |
| `e2e/test_external_query.py` | 1 | Quando habilitado: Gemini, R2, AppTest, contagem e variação mensal contra valores independentes, histórico em schema descartável | Deselecionado por padrão; depende de credenciais, banco `*_test` e duas contagens de referência. Adicionado; **não executado** nesta máquina. |

## Achados priorizados

1. **Alta — falso senso de fluxo completo:** `test_natural_language_service_with_mocked_boundaries` fornecia o plano e a série prontos. Passava com leitor R2 quebrado. O novo teste local atravessa `PNIRemote.dataset`, PyArrow, `GeminiAnalyst.plan`, `SUSExplorer.ask`, cálculo e Streamlit. Uma partição vazia retorna zero; a partição ausente vira `None` e aparece na proveniência. Ainda falta o teste externo executado.
2. **Alta — componentes externos sem prova corrente:** os testes Gemini simulam `generate_content`; o workflow `verify-r2.yml` lista o **cubo de auditoria** em `sus-dados`, não a fonte de consulta `healthbr-data/sipni/microdados`. `test-config.yml` só mostra presença de variáveis. Nenhum desses fluxos prova uma pergunta real de variação mensal no RS.
3. **Alta — skips de PostgreSQL ocultavam a fronteira de persistência:** a primeira execução aprovou sem executar 12 casos de banco. `SUS_EXPLORER_TEST_DB=1` é um gate deliberado contra alteração do banco persistente; não foi desabilitado. O script Windows criou contêiner temporário, executou os 12 casos e o removeu. O workflow CI também declara serviço descartável; execução remota nova não foi observada nesta revisão.
4. **Média — asserção visual fraca:** `test_existing_operations_render_without_backend_initialization` só checava `not at.exception`. Agora verifica valores de métricas e presença de tabela/gráfico conforme a operação. O teste de falha de configuração confirma mensagem genérica sem exposição de detalhe.
5. **Média — confusão entre contrato e semântica:** `test_planner_intent_contract_with_mocked_gemini` retorna o plano esperado do mock; poderia passar se o Gemini real entendesse “variação mensal” como outra operação. O canário externo cobre uma formulação temporal concreta, mas precisa rodar e não representa toda a diversidade linguística.
6. **Baixa — guards estáticos/triviais:** `test_migration_declares_database_enforced_invariants`, `test_paths_are_path_instances` e os dois testes de dataclass não demonstram execução de regra de negócio. Foram mantidos pelo custo baixo e pela função de regressão estrutural, com peso probatório explícito menor. Nenhuma remoção foi justificada por simples presença de mocks.

**Redundância avaliada:** os testes de diferença pura, adaptador e YoY compartilham alguns valores sintéticos, mas exercitam fronteiras distintas (álgebra, contrato de série, referência histórica). Não foi removido nenhum caso sem prova de equivalência comportamental. O teste de nome enganoso foi renomeado; os AppTests continuam necessários para sessão/apresentação.

## Cobertura de comportamento e lacunas

| Área | Evidência atual | Lacuna que ainda pode passar despercebida |
| --- | --- | --- |
| Contagem, agrupamento, série, latência | PyArrow local para count/group/latency, série temporal e filtros; respostas exatas conferidas | Schema/tipos/partições reais de todas as UFs e contagens independentes no R2 |
| MoM/YoY | Janelas, nulos, ausência vs zero, denominador zero, precisão e referência por calendário | Resposta do Gemini a formulações reais e comparações ambíguas |
| Gemini | Schema, parsing, limite de tentativa, erro de transporte e contrato de prompt | Autenticação/indisponibilidade reais, semântica de perguntas temporais em produção |
| PostgreSQL | 12 integrações executadas com banco descartável: leitura/escrita, revisão, idempotência, rollback, privilégio e histórico | Recuperação após reinicialização do servidor e carga/retenção de produção |
| Streamlit | AppTest de estado, submissão, mensagens, tabelas, proveniência e integração local | Navegador real, timeout de serviços externos, experiência sob falha longa |
| Ingestão | Testes sintéticos com Parquet e banco descartável quando habilitado | `co_documento`/schema de partição real e falhas de rede R2 durante leitura |

## Eficácia medida

Com `coverage run --branch --source=sus_explorer,app -m pytest tests -q -rs` contra PostgreSQL descartável, o checkout teve **71% de cobertura total combinada de linhas e branches**; os módulos críticos selecionados somaram **85%**. Por módulo: `temporal.py` 100%, `percentage.py` 97%, `temporal_query.py` 93%, `yoy.py` 96%, `schemas.py` 96%, `llm.py` 93%, `hybrid.py` 94%, `service.py` 76%, `pni.py` 73%, `ingest_r2.py` 78% e `repositories.py` 76%. Na rodada sem banco, os mesmos totais foram 65% e 77%, e ingestão/repositórios ficaram em 48%/29%. Cobertura não mede se expectativas estão corretas.

Uma mutação temporária trocou o fator `100` por `10` em `percentage_changes`. O comando focado `pytest tests/unit/test_percentage.py` terminou com **7 falhas e 8 aprovações**; o arquivo foi restaurado byte a byte e os **15 casos passaram** novamente. Isso demonstra detecção desse defeito específico de escala percentual, não uma pontuação geral de mutação.

## Configuração e documentação

`pytest.ini` define coleta e marcadores e exclui o teste externo da suíte padrão. `.gitignore` ignora `.coverage`/`htmlcov`. `compose.yaml` deixou de versionar uma senha fixa de desenvolvimento e passa a exigir `POSTGRES_PASSWORD` definido pelo operador; `docker compose config --quiet` foi verificado com uma senha temporária de validação. A busca por padrões comuns de chaves vivas em arquivos rastreados não encontrou ocorrência; isso não substitui um scanner especializado nem prova ausência de todos os formatos de segredo.

O README foi reescrito como guia operacional central. Foram incorporados arquitetura, análise temporal, interface, PostgreSQL, histórico, configuração, segurança, comandos e limites antes espalhados por `docs/architecture.md`, `docs/persistence.md`, `docs/streamlit.md`, `docs/temporal_analytics.md`, `docs/temporal_queryplan.md` e `docs/refactor_findings.md`. Esses documentos não foram apagados: contêm cronologia, contratos detalhados e decisões que um resumo operacional não preservaria integralmente. `docs/development_journal.md` é registro histórico e permanece. Nenhum link interno foi removido sem substituição.
