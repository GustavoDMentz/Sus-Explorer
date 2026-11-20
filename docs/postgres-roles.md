# Logins separados no PostgreSQL

Até aqui o app, a ingestão e as migrations usavam o **mesmo usuário**, que no compose é superusuário: qualquer falha no executor ou na ingestão dava controle total do banco, e toda a proteção por papéis (`GRANT`/`REVOKE`, gatilhos de imutabilidade) podia ser contornada. Agora cada tarefa conecta com o **login de menor privilégio** que ela precisa.

## Perfis

| Perfil | Login (padrão) | Grupo | Pode | Usado por |
|---|---|---|---|---|
| `reader` | `sus_explorer_app` | `sus_explorer_reader` | **Só ler**: dados, auditoria de expurgo e a base documental | Consultas do app, catálogo de disponibilidade, busca RAG, `healthcheck` |
| `ingest` | `sus_explorer_ingest` | `sus_explorer_runtime` | Gravar execuções, registros brutos, observações e projeções | `ingest_csv`, `ingest_r2` |
| `history` | `sus_explorer_hist` | `sus_explorer_history` | Só **inserir** no histórico de consultas e de resultados (e atualizar `last_seen_at`/`observations`) | Histórico opcional do app |
| `migrator` | `sus_explorer_admin` | `sus_explorer_migrator` | Dono do schema: migrations, expurgo e indexação RAG | `migrate`, `purge`, `index_knowledge` |

Cada login pertence a **um único grupo**, nenhum é superusuário e nenhum pode criar bancos. O login `migrator` tem `CREATEROLE` com `ADMIN OPTION` apenas sobre os quatro grupos: a migration 002 reafirma os atributos desses papéis e, desde o PostgreSQL 16, isso só funciona sobre papéis que o login administra. O grupo `history` e a titularidade e os privilégios das tabelas da base documental vêm da migration 010.

## Configuração

1. No `.env`, defina as quatro senhas (`POSTGRES_MIGRATOR_PASSWORD`, `POSTGRES_INGEST_PASSWORD`, `POSTGRES_HISTORY_PASSWORD`, `POSTGRES_READER_PASSWORD`) além de `POSTGRES_PASSWORD`. **Nenhuma senha fica no repositório**: o script de bootstrap lê tudo do ambiente e o compose recusa subir sem elas.
2. `docker compose up -d postgres`. Na **primeira** inicialização o container executa `scripts/postgres/init/10-app-roles.sh`, que cria os grupos, os quatro logins e a extensão `vector`. O superusuário de `POSTGRES_USER` serve **só** para esse bootstrap.
3. Rode as migrations com o perfil `migrator`: `python -m sus_explorer.data.persistence.migrate`.
4. Preencha `POSTGRES_<PERFIL>_USER` e `POSTGRES_<PERFIL>_PASSWORD` (os usuários padrão estão no `.env.example`) e ative `POSTGRES_REQUIRE_PROFILES=1`.

Com `POSTGRES_REQUIRE_PROFILES=1`, um perfil sem credenciais é **erro** (a mensagem nomeia as variáveis que faltam) e o login de `POSTGRES_USER` nunca é usado. Com `0` (padrão, para não quebrar instalações existentes), um perfil sem credenciais recorre ao login único, **o que no compose padrão é o superusuário**, e o app registra o evento `postgres_profile_fallback` uma vez por processo e por perfil. Use `1` assim que configurar.

## Instalação existente

O bootstrap só roda em um volume novo. Em um banco já criado, crie os logins uma vez como superusuário, com os mesmos comandos do script (substituindo as variáveis pelas senhas), ou recrie o volume e reimporte. Depois aplique as migrations (`010` entra sozinha) e configure os perfis no `.env`.

## O que isso protege, e o que não

- Uma falha no app (perfil `reader`) não consegue escrever, apagar, criar objetos, desligar gatilhos nem ler a base de histórico.
- A ingestão (`ingest`) não lê a base documental, não cria objetos e não apaga nada.
- O histórico (`history`) não lê dados de vacinação.
- **Não protege** contra credenciais do `migrator` comprometidas: ele é o dono do schema. Mantenha a senha dele só nas máquinas e momentos em que rodam migrations, expurgo e indexação, e não no processo do app.
- Os testes `tests/integration/test_postgres_login_profiles.py` migram um schema novo **como o login migrator**, verificam o que cada login pode e não pode fazer, e rodam o fluxo importação, consulta e expurgo com logins distintos. O script de bootstrap em si (que depende do `initdb` do container) é verificado só estaticamente: sem senha literal, cada login em um único grupo, compose exigindo as senhas.
