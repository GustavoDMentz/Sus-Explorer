# Arquitetura de segurança e privacidade

Visão técnica de **o que foi implementado, como verificar e o que continua em aberto**, a partir da auditoria de segurança de 20/11/2026. Cada peça tem o seu documento; este reúne o mapa, a demonstração e as provas.

- Privacidade dos números: [privacy.md](privacy.md) · Retenção e expurgo: [data-retention.md](data-retention.md)
- Logins do PostgreSQL: [postgres-roles.md](postgres-roles.md) · Reimportação: [persistence.md](persistence.md#reimportação-de-meses-republicados)

## 1. Mapa dos controles

| Camada | Controle | Onde está | PR |
|---|---|---|---|
| **Entrada** | Pergunta normalizada (NFKC), sem controle nem largura zero; 1000 caracteres na UI | `service.py`, `app.py` | #76 |
| | Plano do LLM limitado em **todas** as operações (UF, códigos, textos, idades, `top_n`) | `schemas.py` | #76 |
| | Guarda de coerência município/UF sempre ativo | `llm.py` | #76 |
| **Saída** | Redação de logs (Bearer, URIs `usuário:senha@`, `senha=`, camelCase, CNS) | `operational_logging.py` | #76 |
| | Imagens remotas removidas de texto de terceiros | `text_safety.py` | #77 |
| | **Células pequenas suprimidas (k=5)**, supressão complementar, idade em faixas | `disclosure.py` | #81 |
| **Dados** | **Lista de colunas** guardadas no payload (24 de todas as do CSV) | `payload_policy.py` | #82 |
| | Expurgo auditado, simulação por padrão, retenção de 90 dias das revisões | `purge.py`, migration 009 | #82 |
| | **Reimportação atômica** (uma transação por snapshot), órfãs fechadas | `ingest_csv.py` | #87 |
| | Limites de ZIP (membros, duplicados, caminho, tamanho, compressão 200x) | `zip_guard.py` | #77 |
| **Banco** | **Quatro logins** de menor privilégio (leitura, ingestão, histórico, migração) | `database.py`, migration 010, `scripts/postgres/init/` | #85 |
| | Imagens por digest, lockfile com hashes (`--require-hashes`) | `compose.yaml`, `requirements-lock.txt` | #77, #84, #86 |
| **Rede** | Streamlit só em `127.0.0.1`; Ollama sem redirecionamento e remoto só com opt-in + https; TLS obrigatório fora do localhost | `.streamlit/`, `ollama.py`, `database.py` | #76 |

## 2. Quem conecta com qual privilégio

```mermaid
flowchart LR
    subgraph App["Processo do app (Streamlit)"]
        Q[Consultas e catálogo]
        R[Busca RAG]
        H[Histórico opcional]
    end
    subgraph Jobs["Tarefas administrativas"]
        I[ingest_csv / ingest_r2]
        P[purge / index_knowledge]
        M[migrate]
    end
    Q -->|reader: só SELECT| DB[(PostgreSQL)]
    R -->|reader| DB
    H -->|history: INSERT em 3 tabelas| DB
    I -->|ingest = grupo runtime: grava registros e execuções| DB
    P -->|migrator: dono dos objetos| DB
    M -->|superusuário do bootstrap, só aqui| DB
```

O superusuário (`POSTGRES_USER`) só é usado pelo bootstrap do compose e pelas migrations, porque a migration 002 reafirma `NOSUPERUSER` nos grupos e só um superusuário pode mencionar esse atributo. Isso foi **descoberto pelo CI** ao tentar migrar com um login `CREATEROLE`; o teste `test_migrations_need_a_superuser_and_leave_every_table_to_the_migrator_group` agora o prova.

## 3. Demonstração executável (sem banco)

```bash
python scripts/demo_security.py
```

Saída real, gerada em 20/11/2026 sobre o código da `master`:

```text
## 1. Redação de logs (credenciais nunca chegam ao arquivo)
  'Authorization: Bearer abc123tokenvalue'       -> 'Authorization: [REDACTED]'
  'DB_PASSWORD=hunter2'                          -> 'DB_PASSWORD=[REDACTED]'
  'postgresql://u:pw123@localhost:5432/db'       -> 'postgresql://u:[REDACTED]@localhost:5432/db'
  'senha=abc'                                    -> 'senha=[REDACTED]'
  'secretaria=RS'                                -> 'secretaria=RS'
   {'apiKey': '[REDACTED]', 'accessToken': '[REDACTED]', 'uf': 'RS'}

## 2. Limites do plano gerado pelo LLM (qualquer operação)
  recusado {'uf': 'ZZ'}                           -> ValidationError
  recusado {'municipality_code': '12'}            -> ValidationError
  recusado {'vaccine_text': 'xxxxxxxxx...'}       -> ValidationError
  recusado {'top_n': 101}                         -> ValidationError

## 3. Controle de divulgação (limiar 5)
  contagem 3          -> {'doses': None, 'suppressed': True, 'count_display': 'menos de 5'}
  grupo com célula 3  -> {'rows': [{'value': 'F', 'count': 50}, {'value': 'M', 'count': None,
                          'count_display': 'menos de 5', 'suppressed': True}],
                          'total_after_filters': None, 'total_suppressed': True}
  grupo sem células pequenas -> {'rows': [{'value': 'F', 'count': 50}, {'value': 'M', 'count': 40}],
                                 'total_after_filters': 90}
  latência, 3 registros -> {'n_valid': None, 'median_days': None, 'p90_days': None, 'p95_days': None,
                            'suppressed': True, 'count_display': 'menos de 5'}
  idade 87-87 vira (85, 89) | 18-64 vira (15, 64)

## 4. Lista de colunas guardadas (minimização)
  colunas da entrada : ['co_documento', 'co_municipio_estabelecimento', 'co_paciente', 'co_vacina',
                        'dt_nascimento', 'dt_vacina', 'nu_cep', 'sg_uf_estabelecimento', 'tp_sexo_paciente']
  colunas guardadas  : ['co_documento', 'co_municipio_estabelecimento', 'co_vacina', 'dt_vacina',
                        'sg_uf_estabelecimento', 'tp_sexo_paciente']
  descartadas        : ['co_paciente', 'dt_nascimento', 'nu_cep']

## 5. Leitura de ZIP (zip-slip e zip bomb)
  normal                     -> aceito
  zip-slip                   -> recusado: ZIP com caminho de membro suspeito
  zip bomb (5 MB de zeros)   -> recusado: Razão de compressão do membro do ZIP é suspeita

## 6. Imagens remotas em texto de terceiros (beacon)
  'veja ![x](https://evil.example/p.png) e [link](https://example.org)'
  -> 'veja x e [link](https://example.org)'
```

(As linhas longas foram quebradas aqui para leitura; a saída real é uma linha por item.)

## 4. Prova no banco (CI contra PostgreSQL 17 + pgvector real)

A parte que depende do banco roda no CI. **Última execução na `master`** (commit `7221fe0`, com os três PRs de banco): **668 testes aprovados**, nenhum pulado, run [44668791751](https://github.com/GustavoDMentz/Sus-Explorer/actions/runs/44668791751). Para reproduzir localmente é preciso um PostgreSQL descartável:

```bash
SUS_EXPLORER_TEST_DB=1 POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5432 POSTGRES_DB=sus_explorer_test \
POSTGRES_USER=sus_explorer_test POSTGRES_PASSWORD=<senha-descartável> python -m pytest tests/integration -q
```

| O que se afirma | Teste que prova |
|---|---|
| Um login comum **não** migra; as tabelas ficam com o grupo migrator | `test_migrations_need_a_superuser_and_leave_every_table_to_the_migrator_group` |
| O leitor só lê (inclusive a base documental) | `test_reader_profile_is_read_only_everywhere` |
| O login de histórico só insere histórico e não vê dados de vacinação | `test_history_login_writes_history_only` |
| A ingestão não lê a base documental nem altera estrutura | `test_ingest_login_cannot_read_the_rag_tables` |
| `connect(perfil)` resolve o login certo, sem usar o superusuário | `test_connect_resolves_each_profile_to_its_login_and_refuses_the_superuser` |
| Importação, consulta e expurgo funcionam com logins **distintos** | `test_full_flow_import_query_and_purge_with_separate_logins` |
| Matriz de privilégios por catálogo (nenhum `DELETE`/`TRUNCATE`; leitor sem escrita) | `test_privilege_matrix_reader_is_read_only_and_runtime_cannot_delete` |
| Colunas de resultado imutáveis; erros são mesmo `InsufficientPrivilege` | `test_specific_privilege_errors_for_history_and_result_versions` |
| Funções `SECURITY DEFINER` sem `EXECUTE` público e com `search_path` fixo | `test_security_definer_functions_are_not_public_and_pin_search_path` |
| Só as colunas da lista chegam ao banco, e a versão é registrada | `test_import_stores_only_allowlisted_columns_and_records_the_version` |
| O expurgo é simulação por padrão e fica auditado | `test_purge_is_dry_run_by_default_and_audited` |
| O expurgo remove, a partição fica **indisponível (não zero)**, os gatilhos voltam e dá para reimportar | `test_purge_execute_removes_the_partition_and_it_becomes_unavailable_not_zero` |
| `runtime`/`reader` não conseguem expurgar nem escrever a auditoria | `test_runtime_and_reader_cannot_purge_or_write_the_audit` |
| Um mês republicado **substitui** o anterior, inclusive registros removidos | `test_republished_snapshot_replaces_the_previous_one_including_removed_records` |
| Uma reimportação que falha no meio **desfaz tudo** e o snapshot anterior continua servido | `test_failed_reimport_rolls_back_and_the_previous_snapshot_keeps_being_served` |
| `co_documento` repetido é recusado e nada é confirmado | `test_duplicate_record_keys_in_a_file_are_reported_and_nothing_is_committed` |
| Uma execução órfã é fechada na próxima importação | `test_orphan_running_run_is_closed_and_the_import_proceeds` |

### Verificação manual dos privilégios

Com os logins criados pelo bootstrap, estas consultas mostram a matriz real (rode como superusuário):

```sql
-- O que cada login pode fazer em cada tabela do schema
SELECT r.rolname AS login, c.relname AS tabela,
       has_table_privilege(r.oid, c.oid, 'INSERT') AS ins,
       has_table_privilege(r.oid, c.oid, 'UPDATE') AS upd,
       has_table_privilege(r.oid, c.oid, 'DELETE') AS del
FROM pg_roles r CROSS JOIN pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE r.rolname IN ('sus_explorer_app', 'sus_explorer_ingest', 'sus_explorer_hist', 'sus_explorer_admin')
  AND n.nspname = 'sus_explorer' AND c.relkind = 'r'
ORDER BY r.rolname, c.relname;

-- Os gatilhos de imutabilidade devem estar habilitados ('O')
SELECT tgname, tgenabled FROM pg_trigger
WHERE tgname IN ('raw_revisions_immutable', 'raw_observations_immutable', 'purge_audit_immutable');
```

## 5. Outras evidências

- **Dependências:** `pip-audit` sobre o conjunto instalado do lock (diretas e transitivas): nenhuma vulnerabilidade nos demais pacotes; as únicas ocorrências são do `pip` embutido no ambiente virtual, que não é dependência do projeto (medido na auditoria de 20/11, com 69 pacotes instalados).
- **Análise estática** (medida na auditoria de 20/11, antes das correções posteriores): `bandit` sobre 8.116 linhas, sem `eval`, `exec`, `pickle`, `subprocess`, `shell=True` nem `verify=False`; o único apontamento médio (SQL por f-string no executor) usa fragmentos fixos e uma allowlist.
- **Supply chain:** o CI instala exatamente o lock, com hashes, e as imagens de contêiner estão fixadas por digest; testes (`test_lockfile.py`, `test_supply_chain_pins.py`) quebram se alguém desfizer isso.

## 6. O que isto não resolve

- **Consultas sucessivas** ainda podem ser combinadas para reconstruir uma contagem pequena (privacy.md). Quem expuser o app a terceiros precisa de autenticação e limite de taxa, que não existem.
- **Dados já gravados** antes da lista de colunas mantêm o payload antigo até serem reimportados ou expurgados.
- **O login `migrator` e o superusuário** têm poder total sobre o schema: proteja essas senhas e use-as só nas tarefas administrativas.
- **O script de bootstrap** do compose depende do `initdb` do container e é verificado só de forma estática (sem senha literal, cada login em um grupo, compose exigindo as senhas); o resto é provado contra um banco real.
- **Backups** anteriores a um expurgo continuam com os dados (data-retention.md).
- **Controles do GitHub** (secret scanning, push protection, alertas do Dependabot, proteção da `master`) dependem de configuração do dono do repositório.
