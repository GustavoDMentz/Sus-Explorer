# Documentação do SUS Explorer

Esta pasta contém documentação do estado atual do produto e evidências de validação datadas. Código, migrations e testes permanecem a fonte executável dos contratos.

## Índice oficial

| Arquivo | Finalidade |
| --- | --- |
| [architecture.md](architecture.md) | Componentes, responsabilidades e fluxo de dados |
| [installation.md](installation.md) | Ambiente recomendado e instalação rápida |
| [configuration.md](configuration.md) | Variáveis de ambiente e diagnóstico |
| [database.md](database.md) | Schema, migrations, papéis, retenção e backup |
| [data-sources.md](data-sources.md) | Origem oficial, catálogo e limites dos dados |
| [data-migration.md](data-migration.md) | Download incremental, ingestão, retomada e dimensionamento |
| [rag.md](rag.md) | Indexação, recuperação, síntese e avaliação qualitativa |
| [analytics.md](analytics.md) | Métricas suportadas, semântica e consultas temporais |
| [interface.md](interface.md) | Comportamento funcional da interface Streamlit |
| [testing.md](testing.md) | Níveis de teste, comandos e gates externos |
| [security.md](security.md) | Controles de entrada, banco, logs, RAG e privacidade |
| [privacy.md](privacy.md) | Supressão de células pequenas e risco residual |
| [deployment.md](deployment.md) | Inicialização e operação local recomendada |
| [troubleshooting.md](troubleshooting.md) | Diagnóstico objetivo de falhas comuns |
| [validation/](validation/) | Evidências históricas preservadas, sempre datadas |

## Auditoria dos documentos anteriores

Os 18 arquivos existentes em 25/11/2026 foram lidos e classificados individualmente:

| Arquivo anterior | Conteúdo encontrado | Decisão |
| --- | --- | --- |
| `architecture.md` | Arquitetura ativa PostgreSQL/Ollama/pgvector | Preservado e atualizado |
| `data-retention.md` | Retenção, expurgo e backup | Consolidado em `database.md` |
| `development_journal.md` | Diário cronológico, tentativas, commits e planos antigos | Removido da documentação oficial; evidências atuais permanecem em `validation/` e no Git |
| `local-ai-rag.md` | Instalação e contrato do RAG | Consolidado em `rag.md`, `installation.md` e `configuration.md` |
| `migration-validation-2026-11-08.md` | Evidência real e limites da migração | Preservado em `validation/2026-11-08.md` |
| `opendatasus-sync.md` | Descoberta dos ZIPs e fases futuras | Consolidado em `data-sources.md` e `data-migration.md` |
| `persistence.md` | Schema, ingestão e reimportação | Consolidado em `database.md` e `data-migration.md` |
| `postgres-roles.md` | Papéis de menor privilégio | Consolidado em `database.md` e `security.md` |
| `pr_register.md` | Registro de PRs e convenções de desenvolvimento | Removido; o Git é o registro canônico |
| `privacy.md` | Controle de divulgação | Preservado |
| `query-result-version-history.md` | Especificação anterior à implementação e plano pré-merge | Contrato implementado consolidado em `database.md`; roteiro obsoleto removido |
| `refactor_findings.md` | Achados sobre a arquitetura R2 anterior | Removido; caminho R2 hoje é legado isolado |
| `security-architecture.md` | Controles e demonstrações de segurança | Consolidado em `security.md` |
| `streamlit.md` | Histórico incremental de mudanças da UI | Estado atual consolidado em `interface.md` |
| `technical-guide.md` | Instalação, importação e testes | Dividido entre `installation.md`, `data-migration.md` e `testing.md` |
| `temporal_analytics.md` | Contrato do cálculo temporal | Consolidado em `analytics.md` |
| `temporal_queryplan.md` | Evolução do plano temporal e validações de entrega | Contrato atual consolidado em `analytics.md` |
| `test_audit.md` | Auditoria datada de uma suíte antiga com Gemini/R2 | Substituído por `testing.md`; números históricos obsoletos removidos |

Prompts, transcrições de tarefas e instruções temporárias para agentes não fazem parte da documentação oficial. `AGENTS.md`, caso exista no futuro, deve permanecer na raiz ou no escopo de diretório a que suas regras se aplicam.
