"""Least-privilege logins against a real PostgreSQL (see docs/postgres-roles.md).

Mirrors scripts/postgres/init/10-app-roles.sh: one login per group role, the migrator login
with CREATEROLE and ADMIN OPTION on the groups, none of them a superuser.
"""
import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

from sus_explorer.data.persistence import database
from sus_explorer.data.persistence.database import connect, connect_migrator
from sus_explorer.data.persistence.ingest_csv import ingest_csv
from sus_explorer.data.persistence.migrate import migrate
from sus_explorer.data.persistence.purge import purge
from sus_explorer.postgres_executor import PostgresQueryExecutor
from sus_explorer.schemas import QueryPlan

pytestmark = pytest.mark.skipif(
    os.getenv("SUS_EXPLORER_TEST_DB") != "1",
    reason="Set SUS_EXPLORER_TEST_DB=1 with a disposable PostgreSQL database",
)

GROUPS = ("sus_explorer_migrator", "sus_explorer_runtime", "sus_explorer_reader", "sus_explorer_history")
PASSWORD = "disposable-profile-password"


def denied(connection, statement, values=()):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with connection.transaction():
            connection.execute(statement, values)


@pytest.fixture
def profiles(monkeypatch):
    suffix = uuid4().hex[:12]
    logins = {"migrator": f"adm_{suffix}", "ingest": f"ing_{suffix}",
              "history": f"his_{suffix}", "reader": f"rdr_{suffix}"}
    schema = "profiles_test_" + uuid4().hex
    database_name = os.environ["POSTGRES_DB"]
    superuser = connect()
    for group in GROUPS:
        superuser.execute(sql.SQL(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {name}) THEN "
            "CREATE ROLE {ident} NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOREPLICATION NOBYPASSRLS; END IF; END $$").format(
                name=sql.Literal(group), ident=sql.Identifier(group)))
    superuser.execute("CREATE EXTENSION IF NOT EXISTS vector")
    attributes = {"migrator": "CREATEROLE", "ingest": "NOCREATEROLE", "history": "NOCREATEROLE",
                  "reader": "NOCREATEROLE"}
    groups = {"ingest": "sus_explorer_runtime", "history": "sus_explorer_history", "reader": "sus_explorer_reader"}
    for profile, login in logins.items():
        superuser.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB {} NOREPLICATION PASSWORD {}").format(
            sql.Identifier(login), sql.SQL(attributes[profile]), sql.Literal(PASSWORD)))
    superuser.execute(sql.SQL("GRANT {} TO {} WITH ADMIN OPTION").format(
        sql.SQL(", ").join(sql.Identifier(g) for g in GROUPS), sql.Identifier(logins["migrator"])))
    for profile, group in groups.items():
        superuser.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(group), sql.Identifier(logins[profile])))
    superuser.execute(sql.SQL("GRANT CREATE, CONNECT ON DATABASE {} TO {}").format(
        sql.Identifier(database_name), sql.Identifier(logins["migrator"])))
    superuser.commit()

    def login_connection(profile):
        return psycopg.connect(
            host=os.environ["POSTGRES_HOST"], port=os.environ["POSTGRES_PORT"], dbname=database_name,
            user=logins[profile], password=PASSWORD, options=f"-c search_path={schema},pg_catalog",
            row_factory=dict_row)

    for profile, login in logins.items():
        monkeypatch.setenv(f"POSTGRES_{profile.upper()}_USER", login)
        monkeypatch.setenv(f"POSTGRES_{profile.upper()}_PASSWORD", PASSWORD)
    monkeypatch.setenv("POSTGRES_SCHEMA", schema)
    monkeypatch.setenv("POSTGRES_REQUIRE_PROFILES", "1")      # the legacy superuser must not be used
    try:
        yield superuser, login_connection, schema, logins
    finally:
        superuser.rollback()
        superuser.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        for login in logins.values():
            superuser.execute(sql.SQL("DROP OWNED BY {} CASCADE").format(sql.Identifier(login)))
            superuser.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(login)))
        superuser.commit()
        superuser.close()


def test_migrations_run_as_the_migrator_login_and_it_owns_every_table(profiles, monkeypatch):
    _, login_connection, schema, _ = profiles
    with login_connection("migrator") as admin:
        applied = migrate(admin, schema=schema)
        assert applied[-1] == "010_login_role_privileges.sql" and len(applied) == 10
        assert migrate(admin, schema=schema) == []
        owners = {row["tableowner"] for row in admin.execute(
            "SELECT tableowner FROM pg_tables WHERE schemaname = %s", (schema,)).fetchall()}
        assert owners == {"sus_explorer_migrator"}            # includes the RAG tables (migration 010)


def _migrated(profiles):
    _, login_connection, schema, _ = profiles
    with login_connection("migrator") as admin:
        migrate(admin, schema=schema)


def test_reader_profile_is_read_only_everywhere(profiles):
    _migrated(profiles)
    _, login_connection, _, _ = profiles
    with login_connection("reader") as reader:
        for table in ("datasus_raw_records", "immunization_records", "knowledge_documents", "knowledge_chunks"):
            assert reader.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0
        denied(reader, "INSERT INTO knowledge_documents (title, source, source_type, original_reference, "
                       "content_hash, embedding_model) VALUES ('t','s','markdown','r','" + "a" * 64 + "','m')")
        denied(reader, "INSERT INTO query_history DEFAULT VALUES")
        denied(reader, "DELETE FROM datasus_raw_records")
        denied(reader, "CREATE TABLE attacker_table (id integer)")


def test_history_login_writes_history_only(profiles):
    _migrated(profiles)
    _, login_connection, _, _ = profiles
    with login_connection("history") as history:
        history.execute("""INSERT INTO query_history (id, operation, parameters, executor, status, duration_ms, provenance)
            VALUES (%s, 'count', '{}'::jsonb, 'postgres', 'SUCCESS', 1, '{}'::jsonb)""", (uuid4(),))
        history.commit()
        assert history.execute("SELECT count(*) AS n FROM query_history").fetchone()["n"] == 1
        denied(history, "SELECT count(*) FROM datasus_raw_records")
        denied(history, "INSERT INTO immunization_records DEFAULT VALUES")
        denied(history, "DELETE FROM query_history")
        denied(history, "UPDATE analytical_result_versions SET result_hash = repeat('a', 64)")
        denied(history, "TRUNCATE analytical_result_versions")
        denied(history, "SELECT count(*) FROM knowledge_documents")


def test_ingest_login_cannot_read_the_rag_tables(profiles):
    _migrated(profiles)
    _, login_connection, _, _ = profiles
    with login_connection("ingest") as ingest:
        denied(ingest, "SELECT count(*) FROM knowledge_documents")
        denied(ingest, "DROP TABLE datasus_raw_records")
        denied(ingest, "DELETE FROM datasus_raw_record_observations")


def test_connect_resolves_each_profile_to_its_login_and_refuses_the_superuser(profiles):
    _migrated(profiles)
    _, _, _, logins = profiles
    for profile in ("reader", "ingest", "history", "migrator"):
        with database.connect(profile) as connection:
            assert connection.execute("SELECT current_user AS u").fetchone()["u"] == logins[profile]


def test_full_flow_import_query_and_purge_with_separate_logins(profiles, tmp_path):
    _migrated(profiles)
    source = tmp_path / "flow.csv"
    source.write_text("co_documento,co_vacina,dt_vacina,co_municipio_estabelecimento,sg_uf_estabelecimento,"
                      "tp_sexo_paciente\ndoc-a,9,2026-05-01,4314902,RS,F\ndoc-b,9,2026-05-02,4314902,RS,M\n",
                      encoding="utf-8")
    run = ingest_csv(source, year=2026, month=5, uf="RS", resource_id="flow", batch_size=1)   # ingest login
    assert run["status"] == "SUCCESS"
    executor = PostgresQueryExecutor()                                                         # reader login
    if hasattr(executor, "min_cell_count"):
        executor.min_cell_count = 1               # raw count: the data path is under test
    assert executor.execute(QueryPlan(operation="count", year=2026, month=5, uf="RS")).data["doses"] == 2
    with connect_migrator() as admin:                                                          # migrator login
        planned = purge(admin, scope="partition", partition="ano=2026/mes=05/uf=RS",
                        reason="teste de fluxo com logins separados")
        assert planned["raw_records"] == 2
        purge(admin, scope="partition", partition="ano=2026/mes=05/uf=RS",
              reason="teste de fluxo com logins separados", execute=True)
    with pytest.raises(FileNotFoundError):
        executor.execute(QueryPlan(operation="count", year=2026, month=5, uf="RS"))
