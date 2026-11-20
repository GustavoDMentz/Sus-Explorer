import re
from pathlib import Path

import pytest

from sus_explorer.data.persistence import database

ROOT = Path(__file__).parents[2]


@pytest.fixture
def seen(monkeypatch):
    captured = {}

    def fake_connect(**kwargs):
        captured.update(kwargs)
        raise database.psycopg.OperationalError("stop")
    monkeypatch.setattr(database.psycopg, "connect", fake_connect)
    monkeypatch.setattr(database, "load_dotenv", lambda *a, **k: None)
    for name in ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD",
                 "POSTGRES_REQUIRE_PROFILES", "POSTGRES_SSLMODE"):
        monkeypatch.delenv(name, raising=False)
    for profile in database.PROFILES:
        for suffix in ("USER", "PASSWORD"):
            monkeypatch.delenv(f"POSTGRES_{profile.upper()}_{suffix}", raising=False)
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setattr(database, "_warned_fallback", set())
    return captured


def attempt(profile):
    with pytest.raises(RuntimeError, match="Could not connect"):
        database.connect(profile)


@pytest.mark.parametrize("profile", database.PROFILES)
def test_each_profile_uses_its_own_credentials(seen, monkeypatch, profile):
    monkeypatch.setenv("POSTGRES_USER", "legacy")
    monkeypatch.setenv("POSTGRES_PASSWORD", "legacy-pw")
    monkeypatch.setenv(f"POSTGRES_{profile.upper()}_USER", f"{profile}-login")
    monkeypatch.setenv(f"POSTGRES_{profile.upper()}_PASSWORD", f"{profile}-pw")
    attempt(profile)
    assert (seen["user"], seen["password"]) == (f"{profile}-login", f"{profile}-pw")


def test_profile_falls_back_to_the_legacy_login_with_a_warning(seen, monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "legacy")
    monkeypatch.setenv("POSTGRES_PASSWORD", "legacy-pw")
    events = []
    monkeypatch.setattr(database, "event", lambda name, **kw: events.append((name, kw)))
    attempt("reader")
    attempt("reader")
    assert (seen["user"], seen["password"]) == ("legacy", "legacy-pw")
    warnings = [e for e in events if e[0] == "postgres_profile_fallback"]
    assert len(warnings) == 1 and warnings[0][1]["profile"] == "reader"       # once per process


def test_require_profiles_refuses_the_legacy_login_and_names_the_missing_variables(seen, monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "legacy")
    monkeypatch.setenv("POSTGRES_PASSWORD", "legacy-pw")
    monkeypatch.setenv("POSTGRES_REQUIRE_PROFILES", "1")
    with pytest.raises(RuntimeError, match="POSTGRES_READER_USER, POSTGRES_READER_PASSWORD"):
        database.connect("reader")
    assert "user" not in seen                      # never reached the server with the superuser


def test_a_half_configured_profile_counts_as_missing(seen, monkeypatch):
    monkeypatch.setenv("POSTGRES_REQUIRE_PROFILES", "1")
    monkeypatch.setenv("POSTGRES_READER_USER", "only-the-user")
    with pytest.raises(RuntimeError, match="POSTGRES_READER_PASSWORD"):
        database.connect("reader")


def test_unknown_profile_is_rejected(seen):
    with pytest.raises(RuntimeError, match="Unknown PostgreSQL profile"):
        database.connect("superuser")


def test_legacy_connect_without_a_profile_is_unchanged(seen, monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "legacy")
    monkeypatch.setenv("POSTGRES_PASSWORD", "legacy-pw")
    attempt(None)
    assert (seen["user"], seen["password"]) == ("legacy", "legacy-pw")


def test_call_sites_use_the_least_privileged_profile():
    expectations = {
        "sus_explorer/postgres_executor.py": "connect_reader",
        "sus_explorer/data_catalog.py": "connect_reader",
        "sus_explorer/data/persistence/healthcheck.py": "connect_reader",
        "sus_explorer/data/persistence/ingest_csv.py": "connect_ingest",
        "sus_explorer/data/persistence/ingest_r2.py": "connect_ingest",
        "sus_explorer/data/persistence/history.py": "connect_history",
        "sus_explorer/data/persistence/result_versions.py": "connect_history",
        "sus_explorer/data/persistence/migrate.py": "connect_migrator",
        "sus_explorer/data/persistence/purge.py": "connect_migrator",
    }
    for path, factory in expectations.items():
        text = (ROOT / path).read_text("utf-8")
        assert factory in text, path
        assert not re.search(r"(?<![\w.])connect\(\)", text), f"{path} ainda usa connect() sem perfil"
    rag = (ROOT / "sus_explorer/rag.py").read_text("utf-8")
    assert "connect_reader" in rag and "connect_migrator" in rag
    assert not re.search(r"(?<![\w.])connect\(\)", rag)


def test_bootstrap_script_has_no_literal_passwords_and_requires_every_password():
    script = (ROOT / "scripts/postgres/init/10-app-roles.sh").read_text("utf-8")
    assert "set -euo pipefail" in script
    for name in ("MIGRATOR", "INGEST", "HISTORY", "READER"):
        assert f"POSTGRES_{name}_PASSWORD" in script
    for literal in re.findall(r"PASSWORD\s+'([^']*)'", script):
        pytest.fail(f"senha literal no script: {literal!r}")
    assert re.findall(r"PASSWORD\s+:'", script), "senhas devem vir de variáveis do psql"
    assert "SUPERUSER" in script and "NOSUPERUSER" in script and " SUPERUSER " not in script.replace("NOSUPERUSER", "")


def test_each_login_is_a_member_of_exactly_one_group():
    script = (ROOT / "scripts/postgres/init/10-app-roles.sh").read_text("utf-8")
    grants = re.findall(r"GRANT\s+(sus_explorer_\w+)\s+TO\s+(sus_explorer_\w+);", script)
    members = {}
    for group, login in grants:
        members.setdefault(login, []).append(group)
    assert members == {"sus_explorer_ingest": ["sus_explorer_runtime"],
                       "sus_explorer_hist": ["sus_explorer_history"],
                       "sus_explorer_app": ["sus_explorer_reader"]}
    # the migrator login is granted all groups only WITH ADMIN OPTION (needed by migration 002)
    assert "TO sus_explorer_admin WITH ADMIN OPTION" in script


def test_compose_requires_the_passwords_and_mounts_the_bootstrap_read_only():
    compose = (ROOT / "compose.yaml").read_text("utf-8")
    for name in ("MIGRATOR", "INGEST", "HISTORY", "READER"):
        assert re.search(rf"POSTGRES_{name}_PASSWORD: \$\{{POSTGRES_{name}_PASSWORD:\?", compose), name
    assert "./scripts/postgres/init:/docker-entrypoint-initdb.d:ro" in compose


def test_env_examples_define_profiles_without_secrets():
    for name in (".env.example", ".env.economy.example"):
        text = (ROOT / name).read_text("utf-8")
        for profile in ("MIGRATOR", "INGEST", "HISTORY", "READER"):
            assert re.search(rf"^POSTGRES_{profile}_PASSWORD=$", text, re.M), (name, profile)
            assert re.search(rf"^POSTGRES_{profile}_USER=sus_explorer_\w+$", text, re.M), (name, profile)
        assert re.search(r"^POSTGRES_REQUIRE_PROFILES=0$", text, re.M)
