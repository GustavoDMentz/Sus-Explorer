# Auditoria dos testes não executados — 25/11/2026

Comando: `python -m pytest tests -q -rs`. Resultado após as alterações: 652 aprovados, 38 ignorados e dois externos desmarcados. Os 38 casos têm o mesmo gate deliberado: `SUS_EXPLORER_TEST_DB=1` e PostgreSQL descartável com nome terminado em `_test`. O serviço não estava disponível; forçar o gate violaria a proteção contra uma base persistente.

## `test_postgres_foundation.py` — 27 ignorados

Todos são integração crítica com PostgreSQL/pgvector real; não há problema conhecido demonstrado na suíte isolada.

| Teste | Funcionalidade |
| --- | --- |
| `test_postgres_executor_uses_completed_partition_without_r2` | executor usa snapshot completo sem fallback R2 |
| `test_streaming_csv_import_is_idempotent` | importação CSV e reexecução idempotente |
| `test_official_zip_import_filters_selected_uf_without_extraction` | ZIP nacional filtrado sem extração em disco |
| `test_interrupted_import_leaves_an_orphan_that_the_next_import_closes` | fechamento seguro de run órfão |
| `test_knowledge_vector_cosine_and_foreign_key` | pgvector, cosseno e integridade referencial |
| `test_health_and_query_history_survive_new_connection` | saúde e histórico após nova conexão |
| `test_atomic_raw_normalization_history_and_completion` | transação, revisão e conclusão atômica |
| `test_failed_projection_rolls_back_raw_change` | rollback por falha de projeção |
| `test_failed_migration_rolls_back_and_checksum_is_enforced` | atomicidade e SHA-256 de migration |
| `test_concurrent_migrations_are_serialized` | lock concorrente das migrations |
| `test_runtime_and_reader_least_privilege` | privilégios básicos de runtime/reader |
| `test_runtime_cannot_rewrite_historical_fingerprint` | imutabilidade do fingerprint histórico |
| `test_runtime_authorized_flow_and_finished_run_guards` | fluxo permitido e bloqueio após término |
| `test_database_constraints_and_error_sanitization` | constraints e erros sem detalhes sensíveis |
| `test_privilege_matrix_reader_is_read_only_and_runtime_cannot_delete` | matriz de leitura/escrita/DELETE |
| `test_specific_privilege_errors_for_history_and_result_versions` | restrições dos históricos |
| `test_security_definer_functions_are_not_public_and_pin_search_path` | funções privilegiadas e `search_path` seguro |
| `test_import_stores_only_allowlisted_columns_and_records_the_version` | minimização do payload e versão da allowlist |
| `test_purge_is_dry_run_by_default_and_audited` | expurgo simulado e auditado |
| `test_purge_execute_removes_the_partition_and_it_becomes_unavailable_not_zero` | expurgo real e semântica de indisponibilidade |
| `test_purge_old_revisions_keeps_current_versions` | retenção da revisão atual |
| `test_runtime_and_reader_cannot_purge_or_write_the_audit` | autorização administrativa do expurgo |
| `test_republished_snapshot_replaces_the_previous_one_including_removed_records` | republicação e registros removidos |
| `test_failed_reimport_rolls_back_and_the_previous_snapshot_keeps_being_served` | continuidade durante reimportação falha |
| `test_duplicate_record_keys_in_a_file_are_reported_and_nothing_is_committed` | prevenção de dupla contagem no snapshot |
| `test_orphan_running_run_is_closed_and_the_import_proceeds` | retomada após processo interrompido |
| `test_same_snapshot_is_idempotent_and_does_not_start_a_new_run` | deduplicação do mesmo SHA/snapshot |

## `test_postgres_login_profiles.py` — sete ignorados

| Teste | Funcionalidade |
| --- | --- |
| `test_migrations_need_a_superuser_and_leave_every_table_to_the_migrator_group` | ownership pós-migration |
| `test_reader_profile_is_read_only_everywhere` | reader sem escrita |
| `test_history_login_writes_history_only` | login de histórico restrito |
| `test_ingest_login_cannot_read_the_rag_tables` | separação ingestão/RAG |
| `test_migrator_login_owns_the_schema_objects_through_its_group` | ownership administrativo |
| `test_connect_resolves_each_profile_to_its_login_and_refuses_the_superuser` | resolução dos quatro perfis |
| `test_full_flow_import_query_and_purge_with_separate_logins` | fluxo integral com menor privilégio |

Dependência adicional: permissões para criar papéis e schemas no banco descartável. São críticos para implantação e devem rodar no CI PostgreSQL.

## `test_r2_postgres_ingestion.py` — quatro ignorados

| Teste | Funcionalidade |
| --- | --- |
| `test_initial_rerun_batch_revision_provenance_and_postgres_count` | migração legada, revisão e contagem |
| `test_invalid_rows_and_duplicates_never_claim_complete_coverage` | falhas não viram cobertura completa |
| `test_projection_failure_rolls_back_row_and_marks_run_failed` | rollback e estado FAILED |
| `test_interrupted_run_can_replay_without_duplicate_rows` | retomada sem duplicidade |

Esses testes usam fonte local substituta; comprovam persistência legada, não acesso R2 real. Permanecem relevantes enquanto as ferramentas legadas existirem.

## Dois externos desmarcados

| Teste | Dependências | Prova esperada |
| --- | --- | --- |
| `test_real_index_search_and_generation` | `SUS_EXPLORER_RAG_E2E=1`, banco `*_test`, pgvector e dois modelos Ollama | indexação, embedding, busca, síntese estruturada e referência real |
| `test_real_ollama_postgres_streamlit_count` | `SUS_EXPLORER_EXTERNAL_TEST=1`, banco canário carregado, contagem independente e Ollama | pergunta no AppTest até total PostgreSQL e narrativa real |

O marcador `external` é desmarcado por `pytest.ini`; habilite com `-m external` somente depois de preparar os recursos. Nenhum dos 40 casos foi classificado como dispensável.
